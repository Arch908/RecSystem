"""Leakage-free offline recommendation evaluation and hybrid-weight tuning.

Evaluates against real registered users (excluding ml_placeholder synthetic
accounts) using the live metadata-enriched content-based model, so results
reflect the actual production recommendation pipeline and become more
statistically meaningful as the real user base grows.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, Set

import numpy as np
import pandas as pd
import mysql.connector
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import svds
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from config import DB_CONFIG
from ml.content_based import _movie_document, _build_user_profile


@dataclass
class MetricResult:
    method: str
    k: int
    users_evaluated: int
    precision_at_k: float
    recall_at_k: float
    f1_at_k: float
    ndcg_at_k: float
    diversity_at_k: float
    coverage: float
    hits: int
    relevant_items: int


def _ranking_metrics_at_k(recommended: Iterable[int], relevant: Set[int], k: int):
    """Return Precision, Recall, binary NDCG, hits, and the evaluated top-K list."""
    top_k = list(recommended)[:k]
    hits = len(set(top_k) & relevant)
    precision = hits / k if k else 0.0
    recall = hits / len(relevant) if relevant else 0.0

    dcg = sum(
        1.0 / np.log2(rank + 2)
        for rank, movie_id in enumerate(top_k)
        if movie_id in relevant
    )
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / np.log2(rank + 2) for rank in range(ideal_hits))
    ndcg = dcg / idcg if idcg else 0.0
    return precision, recall, ndcg, hits, top_k


def _genre_set(raw_genres: object) -> Set[str]:
    if pd.isna(raw_genres):
        return set()
    return {
        genre.strip().lower()
        for genre in str(raw_genres).split('|')
        if genre.strip() and genre.strip() != '(no genres listed)'
    }


def _intra_list_diversity(top_k: Iterable[int], movie_genres: Dict[int, Set[str]]) -> float:
    """Average pairwise Jaccard distance among movies in one recommendation list."""
    items = list(top_k)
    if len(items) < 2:
        return 0.0
    distances = []
    for i in range(len(items)):
        left = movie_genres.get(int(items[i]), set())
        for j in range(i + 1, len(items)):
            right = movie_genres.get(int(items[j]), set())
            union = left | right
            similarity = len(left & right) / len(union) if union else 0.0
            distances.append(1.0 - similarity)
    return float(np.mean(distances)) if distances else 0.0


def _minmax(values: pd.Series) -> pd.Series:
    if values.empty:
        return values
    lo, hi = float(values.min()), float(values.max())
    if hi <= lo:
        return pd.Series(0.5, index=values.index, dtype=float)
    return (values - lo) / (hi - lo)


def _finish(method, values, evaluated, relevant_total, k, catalog_size):
    p = values['precision'] / evaluated if evaluated else 0.0
    r = values['recall'] / evaluated if evaluated else 0.0
    f1 = 2*p*r/(p+r) if p+r else 0.0
    ndcg = values['ndcg'] / evaluated if evaluated else 0.0
    diversity = values['diversity'] / evaluated if evaluated else 0.0
    coverage = len(values['recommended_items']) / catalog_size if catalog_size else 0.0
    return MetricResult(
        method, k, evaluated,
        float(round(p,4)), float(round(r,4)), float(round(f1,4)), float(round(ndcg,4)),
        float(round(diversity,4)), float(round(coverage,4)),
        int(values['hits']), relevant_total,
    )


def evaluate_movielens(
    *,
    k: int = 10,
    relevant_threshold: float = 4.0,
    holdout_fraction: float = 0.20,
    min_ratings: int = 10,
    max_users: int = 200,
    random_state: int = 42,
    weight_grid: Iterable[float] = tuple(np.arange(0.50, 0.91, 0.05)),
) -> dict:
    """Leakage-free holdout evaluation against real registered users
    (excludes ml_placeholder accounts), using the live metadata-enriched
    CB model. Kept under the name evaluate_movielens so existing callers
    (the admin evaluation route/UI) work unchanged.
    """
    rng = np.random.default_rng(random_state)

    conn = mysql.connector.connect(**DB_CONFIG)
    ratings = pd.read_sql(
        """
        SELECT r.user_id AS userId, r.movie_id AS movieId, r.rating
        FROM ratings r
        JOIN users u ON u.user_id = r.user_id
        WHERE u.password_hash != 'ml_placeholder'
        ORDER BY r.user_id, r.movie_id
        """,
        conn,
    )
    movies = pd.read_sql(
        """
        SELECT movie_id AS movieId, title, genres, overview, cast, director,
               language, release_date
        FROM movies
        ORDER BY movie_id
        """,
        conn,
    )
    conn.close()

    protocol = {
        'dataset': 'Registered users (live DB, enriched CB model)',
        'split': 'Per-user 20% holdout of ratings >= 4.0',
        'random_state': random_state, 'k': k, 'minimum_user_ratings': min_ratings,
        'maximum_evaluated_users': max_users, 'no_test_leakage': True,
        'selection_metric': 'F1@K',
        'additional_metrics': ['NDCG@K', 'Intra-list diversity', 'Catalog coverage'],
    }

    if ratings.empty:
        return {
            'protocol': protocol,
            'recommended_weights': None,
            'results': [],
            'weight_tuning': [],
            'insufficient_data': True,
            'registered_users_with_ratings': 0,
            'eligible_users': 0,
            'note': 'No registered users have any ratings yet.',
        }

    movie_genres = {int(row.movieId): _genre_set(row.genres) for row in movies.itertuples(index=False)}

    eligible, holdout, train_parts = [], {}, []
    for user_id, group in ratings.groupby('userId'):
        positives = group[group['rating'] >= relevant_threshold]
        if len(group) < min_ratings or len(positives) < 2:
            train_parts.append(group)
            continue
        n_hold = max(1, int(round(len(positives) * holdout_fraction)))
        n_hold = min(n_hold, len(positives) - 1)
        held = rng.choice(positives.index.to_numpy(), size=n_hold, replace=False)
        holdout[int(user_id)] = set(group.loc[held, 'movieId'].astype(int))
        train_parts.append(group.drop(index=held))
        eligible.append(int(user_id))

    registered_users_with_ratings = int(ratings['userId'].nunique())
    MIN_ELIGIBLE_FOR_CF = 5  # SVD needs multiple users to find any collaborative signal

    if len(eligible) < MIN_ELIGIBLE_FOR_CF:
        return {
            'protocol': protocol,
            'recommended_weights': None,
            'results': [],
            'weight_tuning': [],
            'insufficient_data': True,
            'registered_users_with_ratings': registered_users_with_ratings,
            'eligible_users': len(eligible),
            'note': (
                f'{len(eligible)} registered user(s) currently qualify '
                f'(>= {min_ratings} ratings, >= 2 rated {relevant_threshold}+), '
                f'but at least {MIN_ELIGIBLE_FOR_CF} are needed for a meaningful '
                f'collaborative-filtering evaluation. Keep rating movies across '
                f'more accounts to unlock this.'
            ),
        }

    if max_users and len(eligible) > max_users:
        eligible = sorted(rng.choice(eligible, size=max_users, replace=False).tolist())
        holdout = {uid: holdout[uid] for uid in eligible}

    train = pd.concat(train_parts, ignore_index=True)
    all_movie_ids = movies['movieId'].astype(int).tolist()
    movie_to_col = {mid: i for i, mid in enumerate(all_movie_ids)}

    # ── CF: SVD trained fresh on the training split only (no leakage) ──────
    train_cf = train[train['movieId'].isin(movie_to_col)]
    user_ids = sorted(train_cf['userId'].unique().astype(int).tolist())
    user_to_row = {uid: i for i, uid in enumerate(user_ids)}
    rows = train_cf['userId'].map(user_to_row).to_numpy()
    cols = train_cf['movieId'].map(movie_to_col).to_numpy()
    vals = train_cf['rating'].to_numpy(dtype=float)
    sparse = csr_matrix((vals, (rows, cols)), shape=(len(user_ids), len(all_movie_ids)))
    dense = sparse.toarray()
    mask = dense > 0
    counts = mask.sum(axis=1)
    means = np.divide(dense.sum(axis=1), counts, out=np.zeros(len(user_ids)), where=counts > 0)
    demeaned = np.where(mask, dense - means[:, None], 0.0)
    smaller_dim = min(demeaned.shape)
    if smaller_dim < 2:
        cf_pred = np.tile(means[:, None], (1, demeaned.shape[1]))
    elif smaller_dim <= 50:
        # ARPACK's svds is only numerically stable/deterministic when k is
        # comfortably below the matrix's smallest dimension. With few eligible
        # users, rank = smaller_dim - 1 sits right at that edge, and ARPACK can
        # return slightly different results between runs even with a fixed
        # random_state. A dense SVD is fully deterministic and cheap at this
        # scale, so use it whenever the matrix is small.
        rank = min(50, smaller_dim - 1)
        u_full, sigma_full, vt_full = np.linalg.svd(demeaned, full_matrices=False)
        u, sigma, vt = u_full[:, :rank], sigma_full[:rank], vt_full[:rank, :]
        cf_pred = (u * sigma) @ vt + means[:, None]
    else:
        rank = min(50, smaller_dim - 1)
        u, sigma, vt = svds(csr_matrix(demeaned), k=rank, random_state=random_state)
        cf_pred = (u * sigma) @ vt + means[:, None]

    # ── CB: real metadata-enriched model (mirrors live ml/content_based.py) ─
    movies_indexed = movies.set_index('movieId').reindex(all_movie_ids).reset_index()
    movies_indexed['features'] = movies_indexed.apply(_movie_document, axis=1)
    movies_indexed.loc[movies_indexed['features'].str.strip().eq(''), 'features'] = 'unknown_movie'
    tfidf_matrix = TfidfVectorizer(
        stop_words='english', ngram_range=(1, 2), min_df=1, max_df=0.98,
        max_features=60_000, sublinear_tf=True, norm='l2', dtype=np.float32,
    ).fit_transform(movies_indexed['features'])
    cb_movie_indices = {mid: i for i, mid in enumerate(all_movie_ids)}

    def metric_bucket():
        return {'precision': 0.0, 'recall': 0.0, 'ndcg': 0.0, 'diversity': 0.0, 'hits': 0, 'recommended_items': set()}

    base = {name: metric_bucket() for name in ('collaborative', 'content_based')}
    weights = [round(float(w), 2) for w in weight_grid]
    tuning = {w: metric_bucket() for w in weights}
    evaluated = relevant_total = 0

    for uid in eligible:
        if uid not in user_to_row:
            continue
        relevant = holdout[uid]
        user_train = train[train['userId'] == uid]
        seen = set(user_train['movieId'].astype(int))
        candidate = np.array([mid not in seen for mid in all_movie_ids])
        cf_scores = pd.Series(cf_pred[user_to_row[uid]], index=all_movie_ids)[candidate]

        user_train_renamed = user_train.rename(columns={'movieId': 'movie_id'})[['movie_id', 'rating']]
        profile, pos_count, neg_count = _build_user_profile(tfidf_matrix, cb_movie_indices, user_train_renamed)
        if profile is None:
            continue

        cb_scores_full = cosine_similarity(profile.reshape(1, -1), tfidf_matrix)[0]
        cb_scores = pd.Series(cb_scores_full, index=all_movie_ids)[candidate]
        cf_norm, cb_norm = _minmax(cf_scores), _minmax(cb_scores)

        for name, ranked in (
            ('collaborative', cf_scores.sort_values(ascending=False).index.astype(int).tolist()),
            ('content_based', cb_scores.sort_values(ascending=False).index.astype(int).tolist()),
        ):
            p, r, n, h, top_k = _ranking_metrics_at_k(ranked, relevant, k)
            base[name]['precision'] += p; base[name]['recall'] += r; base[name]['ndcg'] += n; base[name]['hits'] += h
            base[name]['diversity'] += _intra_list_diversity(top_k, movie_genres)
            base[name]['recommended_items'].update(top_k)

        for cf_weight in weights:
            scores = cf_weight * cf_norm + (1 - cf_weight) * cb_norm
            ranked = scores.sort_values(ascending=False).index.astype(int).tolist()
            p, r, n, h, top_k = _ranking_metrics_at_k(ranked, relevant, k)
            tuning[cf_weight]['precision'] += p; tuning[cf_weight]['recall'] += r; tuning[cf_weight]['ndcg'] += n; tuning[cf_weight]['hits'] += h
            tuning[cf_weight]['diversity'] += _intra_list_diversity(top_k, movie_genres)
            tuning[cf_weight]['recommended_items'].update(top_k)

        evaluated += 1
        relevant_total += len(relevant)

    catalog_size = len(all_movie_ids)
    results = [_finish(name, vals, evaluated, relevant_total, k, catalog_size) for name, vals in base.items()]
    tuning_rows = []
    for cf_weight, vals in tuning.items():
        item = _finish(f'hybrid_{int(cf_weight*100)}_{int((1-cf_weight)*100)}', vals, evaluated, relevant_total, k, catalog_size)
        row = asdict(item); row.update({'cf_weight': cf_weight, 'cb_weight': round(1 - cf_weight, 2)})
        tuning_rows.append(row)
    best = max(tuning_rows, key=lambda x: (x['f1_at_k'], x['precision_at_k'], x['recall_at_k'])) if tuning_rows else None
    if best:
        results.append(MetricResult('hybrid_tuned', k, evaluated, best['precision_at_k'], best['recall_at_k'], best['f1_at_k'], best['ndcg_at_k'], best['diversity_at_k'], best['coverage'], best['hits'], relevant_total))

    return {
        'protocol': protocol,
        'recommended_weights': (
            {'cf_weight': best['cf_weight'], 'cb_weight': best['cb_weight'],
             'precision_at_k': best['precision_at_k'], 'recall_at_k': best['recall_at_k'],
             'f1_at_k': best['f1_at_k'], 'ndcg_at_k': best['ndcg_at_k'],
             'diversity_at_k': best['diversity_at_k'], 'coverage': best['coverage']}
            if best else None
        ),
        'results': [asdict(x) for x in results],
        'weight_tuning': tuning_rows,
        'insufficient_data': False,
        'registered_users_with_ratings': registered_users_with_ratings,
        'eligible_users': len(eligible),
    }


def save_results(results: dict, output_path: str | Path) -> None:
    Path(output_path).write_text(json.dumps(results, indent=2), encoding='utf-8')