"""Metadata-enriched content-based movie recommender.

The model represents each movie with weighted textual metadata (genres, overview,
director, cast, language, release decade and title) and builds a signed user profile
from likes and dislikes.  It intentionally keeps the TF-IDF matrix sparse so it can
scale to the full MovieLens catalogue without materialising an N x N similarity matrix.

Candidate selection uses a two-stage filter:
  1. Percentile cap   — keep only the top TOP_PERCENTILE of a user's scored candidates,
                         so recommendation-list size stays comparable across users
                         (mirrors the collaborative-filtering module's approach).
  2. Absolute floor    — within that top slice, drop anything below
                         MIN_ABSOLUTE_SIMILARITY (a real, un-normalized cosine value),
                         so a user with scattered taste doesn't get padded with
                         low-confidence matches just to fill a quota.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
import time
from typing import Iterable

import mysql.connector
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DB_CONFIG
from ml.cache_db import ensure_cache_table, get_cached_hash, load_from_db, save_to_db

# New cache key prevents an older title/genre-only model from being reused.
CACHE_KEY = "cb_model_metadata_v2"

POSITIVE_THRESHOLD = 3.5
NEGATIVE_THRESHOLD = 2.5
NEGATIVE_PROFILE_STRENGTH = 0.35

# ── Two-stage candidate selection ───────────────────────────────────────────
# Keep the highest-scoring 2% of a user's unrated candidates (percentile cap,
# same philosophy as ml/collaborative.py's TOP_PERCENTILE), THEN additionally
# require each kept candidate to clear an absolute similarity floor so weak
# matches aren't kept purely to fill the percentile quota.
TOP_PERCENTILE = 0.95
MIN_ABSOLUTE_SIMILARITY = 0.10  # tune using inspect_score_distribution() below

_memory_cache = None


def _clean_text(value: object) -> str:
    """Normalize database text into TF-IDF friendly tokens."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    text = str(value).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _repeat_token(prefix: str, values: Iterable[str], times: int = 1) -> str:
    tokens = []
    for value in values:
        cleaned = _clean_text(value).replace(" ", "_")
        if cleaned:
            tokens.extend([f"{prefix}_{cleaned}"] * times)
    return " ".join(tokens)


def _movie_document(row: pd.Series) -> str:
    """Create one weighted metadata document for a movie.

    Repeating prefixed tokens is a simple, interpretable way to give structured
    fields more influence than free-form overview words.
    """
    title = re.sub(r"\s*\(\d{4}\)\s*$", "", str(row.get("title") or ""))
    genres = [g for g in str(row.get("genres") or "").split("|") if g and g != "(no genres listed)"]
    cast = [name.strip() for name in str(row.get("cast") or "").split(",") if name.strip()][:8]
    directors = [name.strip() for name in str(row.get("director") or "").split(",") if name.strip()][:3]

    release_date = row.get("release_date")
    year = None
    if pd.notna(release_date):
        try:
            year = pd.to_datetime(release_date).year
        except (TypeError, ValueError):
            year = None
    if not year:
        match = re.search(r"\((\d{4})\)", str(row.get("title") or ""))
        year = int(match.group(1)) if match else None

    parts = [
        _repeat_token("genre", genres, times=4),
        _repeat_token("director", directors, times=3),
        _repeat_token("cast", cast, times=2),
        _repeat_token("language", [str(row.get("language") or "")], times=2),
        f"decade_{(year // 10) * 10}" if year else "",
        f"title_{_clean_text(title).replace(' ', '_')}",
        _clean_text(title),
        _clean_text(row.get("overview")),
    ]
    return " ".join(part for part in parts if part)


def get_movies_hash() -> str:
    """Fingerprint all metadata fields used by the model.

    Hashing only the row count would not invalidate the cache when an overview,
    cast member or genre changes.  This aggregate fingerprint refreshes the model
    when relevant metadata changes without loading every row into Python solely
    for hashing.
    """
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COUNT(*), COALESCE(MAX(movie_id), 0),
               COALESCE(SUM(CHAR_LENGTH(COALESCE(title, ''))), 0),
               COALESCE(SUM(CHAR_LENGTH(COALESCE(genres, ''))), 0),
               COALESCE(SUM(CHAR_LENGTH(COALESCE(overview, ''))), 0),
               COALESCE(SUM(CHAR_LENGTH(COALESCE(cast, ''))), 0),
               COALESCE(SUM(CHAR_LENGTH(COALESCE(director, ''))), 0)
        FROM movies
        """
    )
    fingerprint = cursor.fetchone()
    cursor.close()
    conn.close()
    return hashlib.md5(repr(fingerprint).encode("utf-8")).hexdigest()


def build_content_model(built_by=None):
    print("[CB] Building metadata-enriched content model...")
    started = time.time()

    conn = mysql.connector.connect(**DB_CONFIG)
    movies = pd.read_sql(
        """
        SELECT movie_id, title, genres, overview, cast, director,
               language, release_date
        FROM movies
        ORDER BY movie_id
        """,
        conn,
    )
    conn.close()

    if movies.empty:
        return None

    movies["features"] = movies.apply(_movie_document, axis=1)
    # A fallback token prevents an empty-vocabulary error for incomplete records.
    movies.loc[movies["features"].str.strip().eq(""), "features"] = "unknown_movie"

    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        min_df=1,
        max_df=0.98,
        max_features=60_000,
        sublinear_tf=True,
        norm="l2",
        dtype=np.float32,
    )
    tfidf_matrix = vectorizer.fit_transform(movies["features"])
    movie_indices = pd.Series(movies.index, index=movies["movie_id"]).to_dict()

    current_hash = get_movies_hash()
    model = {
        "tfidf_matrix": tfidf_matrix,
        "movie_indices": movie_indices,
        "movies": movies,
        "vectorizer": vectorizer,
        "movies_hash": current_hash,
        "built_at": time.time(),
        "model_version": 2,
        "feature_count": int(tfidf_matrix.shape[1]),
    }

    save_to_db(CACHE_KEY, current_hash, model, built_by=built_by)
    print(
        f"[CB] Built {len(movies):,} movies x {tfidf_matrix.shape[1]:,} features "
        f"in {time.time() - started:.1f}s"
    )
    return model


def get_or_build_model(built_by=None):
    global _memory_cache
    current_hash = get_movies_hash()

    if _memory_cache and _memory_cache.get("movies_hash") == current_hash:
        return _memory_cache

    ensure_cache_table()
    if get_cached_hash(CACHE_KEY) == current_hash:
        cached = load_from_db(CACHE_KEY)
        if cached and cached.get("model_version") == 2:
            _memory_cache = cached
            print("[CB] Loaded metadata-enriched model from DB cache.")
            return cached

    _memory_cache = build_content_model(built_by=built_by)
    return _memory_cache


def _weighted_centroid(matrix, rows: list[int], weights: np.ndarray):
    if not rows or weights.size == 0 or float(weights.sum()) <= 0:
        return None
    return (matrix[rows].T @ weights) / float(weights.sum())


def _build_user_profile(tfidf_matrix, movie_indices: dict, ratings: pd.DataFrame):
    """Build a profile that rewards likes and gently moves away from dislikes."""
    positive_rows, positive_weights = [], []
    negative_rows, negative_weights = [], []

    for row in ratings.itertuples(index=False):
        idx = movie_indices.get(int(row.movie_id))
        if idx is None:
            continue
        rating = float(row.rating)
        if rating >= POSITIVE_THRESHOLD:
            positive_rows.append(idx)
            # 3.5 -> 0.5, 5.0 -> 2.0
            positive_weights.append(rating - 3.0)
        elif rating <= NEGATIVE_THRESHOLD:
            negative_rows.append(idx)
            # 2.5 -> 0.5, 0.5 -> 2.5
            negative_weights.append(3.0 - rating)

    # If the user has no explicit likes, use ratings above their own mean so the
    # model can still form a relative preference profile.
    if not positive_rows and not ratings.empty:
        user_mean = float(ratings["rating"].mean())
        for row in ratings.itertuples(index=False):
            idx = movie_indices.get(int(row.movie_id))
            if idx is not None and float(row.rating) >= user_mean:
                positive_rows.append(idx)
                positive_weights.append(max(float(row.rating) - user_mean + 0.25, 0.25))

    positive = _weighted_centroid(
        tfidf_matrix, positive_rows, np.asarray(positive_weights, dtype=np.float32)
    )
    if positive is None:
        return None, 0, 0

    negative = _weighted_centroid(
        tfidf_matrix, negative_rows, np.asarray(negative_weights, dtype=np.float32)
    )
    profile = positive
    if negative is not None:
        profile = positive - NEGATIVE_PROFILE_STRENGTH * negative

    return profile, len(positive_rows), len(negative_rows)


def _select_top_candidates(scores: pd.Series) -> tuple[pd.Series, float | None]:
    """Two-stage selection: percentile cap, then an absolute similarity floor.

    Returns (selected_scores_sorted_desc, percentile_threshold_used).
    percentile_threshold_used is None if there were no finite positive scores.
    """
    finite_scores = scores[np.isfinite(scores) & (scores > 0)]
    if finite_scores.empty:
        return finite_scores, None

    # Stage 1 — percentile cap (bounds the maximum list size, like CF).
    percentile_threshold = float(np.percentile(finite_scores.values, TOP_PERCENTILE * 100))
    top_slice = finite_scores[finite_scores >= percentile_threshold]

    # Stage 2 — absolute quality floor (drops weak matches within that slice).
    quality_filtered = top_slice[top_slice >= MIN_ABSOLUTE_SIMILARITY]

    return quality_filtered.sort_values(ascending=False), percentile_threshold


def get_cb_recommendations(user_id, n=None):
    model = get_or_build_model()
    if not model:
        return []

    tfidf_matrix = model["tfidf_matrix"]
    movie_indices = model["movie_indices"]
    movies = model["movies"]

    conn = mysql.connector.connect(**DB_CONFIG)
    ratings = pd.read_sql(
        "SELECT movie_id, rating FROM ratings WHERE user_id = %s",
        conn,
        params=(int(user_id),),
    )
    conn.close()

    if ratings.empty:
        return []

    profile, positive_count, negative_count = _build_user_profile(
        tfidf_matrix, movie_indices, ratings
    )
    if profile is None:
        return []

    raw_scores = cosine_similarity(profile.reshape(1, -1), tfidf_matrix)[0]
    scores = pd.Series(raw_scores, index=movies["movie_id"].astype(int).to_numpy())
    scores = scores[~scores.index.isin(set(ratings["movie_id"].astype(int)))]

    ranked, percentile_threshold = _select_top_candidates(scores)

    if ranked.empty:
        print(
            f"[CB] user={user_id} has no candidates clearing both the "
            f"top-{int((1 - TOP_PERCENTILE) * 100)}% percentile cap and the "
            f"absolute floor ({MIN_ABSOLUTE_SIMILARITY})"
        )
        return []

    if n is not None:
        ranked = ranked.head(max(1, int(n)))

    movie_lookup = movies.set_index("movie_id")
    recommendations = []
    for movie_id, raw_score in ranked.items():
        row = movie_lookup.loc[movie_id]
        recommendations.append(
            {
                "movie_id": int(movie_id),
                "score": float(raw_score),
                "raw_content_score": float(raw_score),
                "method": "content",
                "content_signals": {
                    "genres": [g for g in str(row.get("genres") or "").split("|") if g],
                    "director": str(row.get("director") or ""),
                    "language": str(row.get("language") or ""),
                },
            }
        )

    threshold_text = f"{percentile_threshold:.4f}" if percentile_threshold is not None else "n/a"
    print(
        f"[CB] user={user_id} likes={positive_count} dislikes={negative_count} "
        f"percentile_threshold={threshold_text} "
        f"absolute_floor={MIN_ABSOLUTE_SIMILARITY} "
        f"candidates={len(recommendations)} "
        f"metadata_features={model.get('feature_count', 0)}"
    )
    return recommendations


def get_similar_movies(movie_id: int, n: int = 12) -> list:
    """Movie-to-movie similarity, used by the MovieDetail 'Similar Movies' section."""
    model = get_or_build_model()
    if not model:
        return []

    tfidf_matrix = model["tfidf_matrix"]
    movie_indices = model["movie_indices"]
    movies = model["movies"]

    idx = movie_indices.get(int(movie_id))
    if idx is None:
        return []

    sims = cosine_similarity(tfidf_matrix[idx], tfidf_matrix).flatten()
    movie_ids = movies["movie_id"].astype(int).to_numpy()
    order = np.argsort(-sims)

    results = []
    for pos in order:
        candidate_id = int(movie_ids[pos])
        if candidate_id == int(movie_id):
            continue
        score = float(sims[pos])
        if score <= 0:
            continue
        results.append({"movie_id": candidate_id, "similarity_score": round(score, 6)})
        if len(results) >= n:
            break
    return results


# ── Calibration helper ──────────────────────────────────────────────────────

def inspect_score_distribution(user_id: int) -> None:
    """Print a raw similarity-score distribution for one user.

    Run this from a Python shell (with app context / DB configured) to see what
    MIN_ABSOLUTE_SIMILARITY should realistically be for your vocabulary/weighting
    scheme, e.g.:

        python -c "from ml.content_based import inspect_score_distribution as f; f(10001)"
    """
    model = get_or_build_model()
    if not model:
        print("No model available.")
        return

    tfidf_matrix = model["tfidf_matrix"]
    movie_indices = model["movie_indices"]
    movies = model["movies"]

    conn = mysql.connector.connect(**DB_CONFIG)
    ratings = pd.read_sql(
        "SELECT movie_id, rating FROM ratings WHERE user_id = %s",
        conn,
        params=(int(user_id),),
    )
    conn.close()

    if ratings.empty:
        print(f"User {user_id} has no ratings.")
        return

    profile, pos, neg = _build_user_profile(tfidf_matrix, movie_indices, ratings)
    if profile is None:
        print(f"User {user_id} — could not build a profile.")
        return

    raw_scores = cosine_similarity(profile.reshape(1, -1), tfidf_matrix)[0]
    scores = pd.Series(raw_scores, index=movies["movie_id"].astype(int).to_numpy())
    scores = scores[~scores.index.isin(set(ratings["movie_id"].astype(int)))]
    finite = scores[np.isfinite(scores) & (scores > 0)]

    print(f"user={user_id} likes={pos} dislikes={neg} candidates={len(finite)}")
    print(f"  min={finite.min():.4f}  p50={finite.median():.4f}  "
          f"p90={np.percentile(finite, 90):.4f}  p98={np.percentile(finite, 98):.4f}  "
          f"max={finite.max():.4f}")