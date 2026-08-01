"""
ml/hybrid.py — Hybrid recommendation scoring.

Combines Collaborative Filtering (SVD) and Content-Based (TF-IDF cosine)
scores into a single ranked list using min-max normalization + weighted fusion.

Weights: CF 60% + CB 40%
  - CF is SVD-trained on 50k MovieLens ratings → stronger personalization signal
  - CB is TF-IDF on title+genres only → weaker but useful for filling CF gaps

Score formula (for movies in BOTH):
    hybrid = CF_WEIGHT * cf_norm + CB_WEIGHT * cb_norm

Score formula (for movies in ONE only):
    hybrid = present_weight * score_norm
    (penalized since only one signal supports it)
"""

import numpy as np

# ── Fixed hybrid weights ───────────────────────────────────────────────────
CF_WEIGHT = 0.60
CB_WEIGHT = 0.40


# When only one signal is present, apply this penalty multiplier.
# 0.85 means a CF-only movie can score at most 0.85 in hybrid space,
# preventing single-signal movies from outranking dual-signal ones.
SINGLE_SIGNAL_PENALTY = 0.85


def _minmax_normalize(score_dict: dict) -> dict:
    """
    Min-max normalize a {movie_id: score} dict to [0, 1].
    Returns the same dict unchanged if all values are equal.
    """
    if not score_dict:
        return {}
    values = np.array(list(score_dict.values()), dtype=float)
    vmin, vmax = values.min(), values.max()
    if vmax <= vmin:
        # All scores identical — return uniform 0.5
        return {mid: 0.5 for mid in score_dict}
    return {
        mid: float((score - vmin) / (vmax - vmin))
        for mid, score in score_dict.items()
    }


def compute_hybrid_scores(cf_recs: list, cb_recs: list, cf_weight: float = None, cb_weight: float = None) -> list:
    """
    Merge CF and CB recommendation lists into a single hybrid-scored list.

    Returns
    -------
    list of dicts sorted by hybrid_score descending:
        {
          'movie_id'      : int,
          'score'         : float,        # normalized hybrid score — used for ranking only
          'cf_score'      : float | None, # normalized CF score (0-1) — ranking only
          'cb_score'      : float | None, # normalized CB score (0-1) — ranking only
          'cf_score_raw'  : float | None, # raw SVD predicted rating (0.5-5.0) — for display
          'cb_score_raw'  : float | None, # raw cosine similarity (0-1) — for display
          'method'        : 'collaborative' | 'content' | 'both',
        }
    """
    if not cf_recs and not cb_recs:
        return []

    cf_weight = CF_WEIGHT if cf_weight is None else float(cf_weight)
    cb_weight = CB_WEIGHT if cb_weight is None else float(cb_weight)
    total_weight = cf_weight + cb_weight
    if total_weight <= 0:
        raise ValueError('Hybrid weights must sum to a positive value')
    cf_weight, cb_weight = cf_weight / total_weight, cb_weight / total_weight

    # Raw (un-normalized) score dicts — kept for human-readable display.
    cf_raw = {r['movie_id']: r['score'] for r in cf_recs}
    cb_raw = {r['movie_id']: r['score'] for r in cb_recs}

    # Normalized 0-1 versions — used only for ranking/blending.
    cf_norm = _minmax_normalize(cf_raw)
    cb_norm = _minmax_normalize(cb_raw)

    all_movie_ids = set(cf_norm) | set(cb_norm)

    results = []
    for mid in all_movie_ids:
        has_cf = mid in cf_norm
        has_cb = mid in cb_norm

        cf_s = cf_norm.get(mid)
        cb_s = cb_norm.get(mid)

        if has_cf and has_cb:
            hybrid = cf_weight * cf_s + cb_weight * cb_s
            method = 'both'
        elif has_cf:
            hybrid = cf_weight * cf_s * SINGLE_SIGNAL_PENALTY
            method = 'collaborative'
        else:
            hybrid = cb_weight * cb_s * SINGLE_SIGNAL_PENALTY
            method = 'content'

        results.append({
            'movie_id': int(mid),
            'score': round(hybrid, 6),
            'cf_score': round(cf_s, 6) if cf_s is not None else None,
            'cb_score': round(cb_s, 6) if cb_s is not None else None,
            'cf_score_raw': round(cf_raw[mid], 4) if has_cf else None,
            'cb_score_raw': round(cb_raw[mid], 4) if has_cb else None,
            'method': method,
        })

    results.sort(key=lambda x: x['score'], reverse=True)
    return results


def get_hybrid_recommendations(user_id: int, n: int = None) -> list:
    """
    Main entry point. Fetches CF + CB recs, merges them via hybrid scoring.

    Parameters
    ----------
    user_id : int
    n       : int | None — if set, cap the returned list at n items

    Returns
    -------
    list of hybrid-scored recommendation dicts (see compute_hybrid_scores)
    """
    # Import here to avoid circular imports at module load time
    from ml.collaborative import get_cf_recommendations
    from ml.content_based import get_cb_recommendations

    cf_recs = get_cf_recommendations(user_id)
    cb_recs = get_cb_recommendations(user_id)

    cf_count = len(cf_recs)
    cb_count = len(cb_recs)

    merged = compute_hybrid_scores(cf_recs, cb_recs)

    both_count = sum(1 for r in merged if r['method'] == 'both')
    print(
        f"[Hybrid] user={user_id} | CF={cf_count} CB={cb_count} "
        f"→ merged={len(merged)} (both={both_count}) "
        f"weights=CF{int(CF_WEIGHT*100)}/CB{int(CB_WEIGHT*100)}"
    )

    if n:
        merged = merged[:n]

    return merged