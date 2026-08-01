"""Collaborative-filtering recommender using SVD matrix factorization.

Candidate selection uses a two-stage filter, mirroring ml/content_based.py:
  1. Percentile cap — keep only the top TOP_PERCENTILE of a user's predicted
                       scores, so recommendation-list size stays bounded and
                       comparable across users.
  2. Absolute floor  — within that top slice, drop anything whose predicted
                       rating is below MIN_ABSOLUTE_PREDICTED_SCORE. Because
                       SVD predictions sit on the same 0.5-5.0 scale as real
                       ratings, this floor is directly interpretable (and
                       matches the 3.5 "positive rating" threshold used
                       elsewhere in the app, e.g. content_based.py and the
                       admin rec-accuracy dashboard).
"""
import time
import hashlib
import pandas as pd
import numpy as np
from scipy.sparse.linalg import svds
from scipy.sparse import csr_matrix
import mysql.connector
from config import DB_CONFIG
from ml.cache_db import ensure_cache_table, load_from_db, save_to_db, get_cached_hash

CACHE_KEY = 'svd_model'

# ── Two-stage candidate selection ───────────────────────────────────────────
TOP_PERCENTILE = 0.95               # keep the top 2% of a user's predicted scores
MIN_ABSOLUTE_PREDICTED_SCORE = 3.68  # ...but only if SVD predicts >= 3.5 stars


_memory_cache = None


def get_ratings_hash():
    conn   = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), COALESCE(MAX(id), 0) FROM ratings")
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return hashlib.md5(str(row).encode()).hexdigest()


def get_ml_user_ids():
    conn   = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id FROM users WHERE password_hash = 'ml_placeholder'"
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return {row[0] for row in rows}


def build_svd_model(built_by=None):
    print("[CF] Building SVD model...")
    t0 = time.time()

    ml_user_ids = get_ml_user_ids()
    if not ml_user_ids:
        print("[CF] No ML users found.")
        return None

    conn = mysql.connector.connect(**DB_CONFIG)
    df   = pd.read_sql(
        f"SELECT user_id, movie_id, rating FROM ratings "
        f"WHERE user_id IN ({','.join(map(str, ml_user_ids))})",
        conn
    )
    conn.close()

    if df.empty:
        return None

    user_ids  = df['user_id'].unique()
    movie_ids = df['movie_id'].unique()

    user_idx  = {uid: i for i, uid in enumerate(user_ids)}
    movie_idx = {mid: i for i, mid in enumerate(movie_ids)}

    rows   = df['user_id'].map(user_idx)
    cols   = df['movie_id'].map(movie_idx)
    matrix = csr_matrix((df['rating'].values, (rows, cols)),
                         shape=(len(user_ids), len(movie_ids)))

    matrix_dense  = matrix.toarray()
    user_means    = np.mean(matrix_dense, axis=1)
    matrix_demean = matrix_dense - user_means.reshape(-1, 1)

    k = min(50, min(matrix_demean.shape) - 1)
    U, sigma, Vt = svds(matrix_demean, k=k, random_state=42)
    sigma_diag   = np.diag(sigma)

    predicted    = np.dot(np.dot(U, sigma_diag), Vt) + user_means.reshape(-1, 1)
    predicted_df = pd.DataFrame(predicted, index=user_ids, columns=movie_ids)

    current_hash = get_ratings_hash()
    obj = {
        'predicted_df': predicted_df,
        'ratings_hash': current_hash,
        'built_at':     time.time(),
        'movie_ids':    list(movie_ids),
        'Vt':           Vt,
        'sigma':        sigma,
        'global_mean':  df['rating'].mean(),
    }

    save_to_db(CACHE_KEY, current_hash, obj, built_by=built_by)
    print(f"[CF] SVD built in {time.time()-t0:.1f}s")
    return obj


def get_or_build_model(built_by=None):
    global _memory_cache
    current_hash = get_ratings_hash()

    if _memory_cache and _memory_cache.get('ratings_hash') == current_hash:
        return _memory_cache

    ensure_cache_table()
    cached_hash = get_cached_hash(CACHE_KEY)
    if cached_hash == current_hash:
        obj = load_from_db(CACHE_KEY)
        if obj:
            _memory_cache = obj
            print("[CF] Loaded SVD from DB cache.")
            return obj

    obj = build_svd_model(built_by=built_by)
    if obj:
        _memory_cache = obj
    return obj


def get_user_ratings_vector(user_id, movie_ids):
    conn = mysql.connector.connect(**DB_CONFIG)
    df   = pd.read_sql(
        f"SELECT movie_id, rating FROM ratings WHERE user_id = {user_id}", conn
    )
    conn.close()

    vector    = np.zeros(len(movie_ids))
    movie_idx = {mid: i for i, mid in enumerate(movie_ids)}

    for _, row in df.iterrows():
        mid = row['movie_id']
        if mid in movie_idx:
            vector[movie_idx[mid]] = row['rating']

    return vector, set(df['movie_id'].tolist())


def fold_in_user(user_id, cache):
    """
    Project a registered user into SVD latent space using fold-in.
    r_new ≈ u_new × Σ × Vt
    u_new = r_new × Vt.T × Σ_inv
    predicted = u_new × Σ × Vt + user_mean
    """
    Vt        = cache['Vt']
    sigma     = cache['sigma']
    movie_ids = cache['movie_ids']

    user_vector, already_rated = get_user_ratings_vector(user_id, movie_ids)

    rated_count = (user_vector > 0).sum()
    print(f"[CF] User {user_id} has {rated_count} ratings in SVD movie space")

    if rated_count < 3:
        print(f"[CF] Not enough ratings ({rated_count}/3 needed)")
        return None, set()

    user_mean  = user_vector[user_vector > 0].mean()
    r_demeaned = user_vector.copy()
    r_demeaned[r_demeaned > 0] -= user_mean

    sigma_inv = 1.0 / sigma
    u_new     = r_demeaned @ Vt.T * sigma_inv
    predicted = (u_new * sigma) @ Vt + user_mean

    scores_series = pd.Series(predicted, index=movie_ids)
    return scores_series, already_rated


def _select_top_candidates(scores_series, already_rated):
    """Two-stage selection: percentile cap, then an absolute predicted-rating floor.

    Returns (selected_scores_sorted_desc, percentile_threshold_used).
    percentile_threshold_used is None if there were no finite unrated candidates.
    """
    unrated = scores_series[~scores_series.index.isin(already_rated)]
    unrated = unrated[np.isfinite(unrated)]
    if unrated.empty:
        return unrated, None

    # Stage 1 — percentile cap (bounds the maximum list size).
    percentile_threshold = float(np.percentile(unrated.values, TOP_PERCENTILE * 100))
    top_slice = unrated[unrated >= percentile_threshold]

    # Stage 2 — absolute quality floor (drops weak matches within that slice).
    quality_filtered = top_slice[top_slice >= MIN_ABSOLUTE_PREDICTED_SCORE]

    return quality_filtered.sort_values(ascending=False), percentile_threshold


def get_cf_recommendations(user_id, n=None):
    cache = get_or_build_model()
    if not cache:
        return []

    predicted_df = cache['predicted_df']

    # ── Case 1: ML user — direct lookup ───────────────────────────────────
    if user_id in predicted_df.index:
        conn = mysql.connector.connect(**DB_CONFIG)
        df   = pd.read_sql(
            f"SELECT movie_id FROM ratings WHERE user_id = {user_id}", conn
        )
        conn.close()
        already_rated = set(df['movie_id'].tolist())
        scores_series = predicted_df.loc[user_id]

    # ── Case 2: Registered user — fold-in ─────────────────────────────────
    else:
        print(f"[CF] Registered user {user_id} — using fold-in...")
        scores_series, already_rated = fold_in_user(user_id, cache)
        if scores_series is None:
            return []

    top_scores, percentile_threshold = _select_top_candidates(
        scores_series, already_rated
    )
    if n is not None:
        top_scores = top_scores.head(max(1, int(n)))

    recs = []
    for movie_id, score in top_scores.items():
        recs.append({
            'movie_id': int(movie_id),
            'score':    float(score),
            'method':   'collaborative'
        })

    threshold_text = (
        f"{percentile_threshold:.3f}" if percentile_threshold is not None else "n/a"
    )
    print(
        f"[CF] user={user_id} top_percentile={TOP_PERCENTILE:.2f} "
        f"percentile_threshold={threshold_text} "
        f"absolute_floor={MIN_ABSOLUTE_PREDICTED_SCORE} "
        f"candidates={len(recs)}"
    )
    return recs