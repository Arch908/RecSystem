from flask import Blueprint, jsonify, request, session
import re
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from models.db import (
    get_movies_paginated, get_trending_movies, get_all_genres,
    save_rating, get_user_ratings, get_watchlist_ids,
    add_to_watchlist, remove_from_watchlist, get_watchlist,
    get_connection, get_movie_ratings_stats, get_not_interested_ids,
    add_not_interested, remove_not_interested,
    get_user_onboarding_status, save_favorite_genres,
    mark_onboarding_complete_if_ready, get_onboarding_movies
)

api_bp = Blueprint('api', __name__, url_prefix='/api')


def login_required_api(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        return f(*args, **kwargs)
    return decorated


# ── Auth ───────────────────────────────────────────────────────────────────

@api_bp.route('/auth/login', methods=['POST'])
def login():
    data     = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if user and user['password_hash'] == 'ml_placeholder':
        return jsonify({'error': 'Invalid credentials'}), 401

    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({'error': 'Invalid username or password'}), 401

    if user.get('is_banned'):
        return jsonify({'error': 'Account suspended. Contact support.'}), 403

    session['user_id']  = user['user_id']
    session['username'] = user['username']
    session['is_admin'] = bool(user.get('is_admin', 0))

    onboarding = get_user_onboarding_status(user['user_id'])

    return jsonify({
        'authenticated': True,
        'user_id': user['user_id'],
        'username': user['username'],
        'is_admin': bool(user.get('is_admin', 0)),
        'favorite_genres': onboarding.get('favorite_genres', []),
        'rating_count': onboarding.get('rating_count', 0),
        'ratings_needed': onboarding.get('ratings_needed', 10),
        'onboarding_complete': onboarding.get('onboarding_complete', False),
    })


@api_bp.route('/auth/register', methods=['POST'])
def register():
    data     = request.get_json()
    username = data.get('username', '').strip()
    email    = data.get('email', '').strip()
    password = data.get('password', '')

    if not username or not email or not password:
        return jsonify({'error': 'All fields required'}), 400
    if not re.fullmatch(r'[A-Za-z0-9_]{3,30}', username):
        return jsonify({'error': 'Username must be 3-30 letters, numbers, or underscores'}), 400
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        return jsonify({'error': 'Enter a valid email address'}), 400
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400

    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
            (username, email.lower(), generate_password_hash(password))
        )
        conn.commit()
        return jsonify({'message': 'Registration successful'}), 201
    except mysql.connector.IntegrityError:
        return jsonify({'error': 'Username or email already exists'}), 409
    except mysql.connector.Error as e:
        print(f"[DB ERROR] {e}")  # will show in Render logs
        return jsonify({'error': 'Registration service is temporarily unavailable'}), 503

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@api_bp.route('/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logged out'})


@api_bp.route('/auth/me')
def me():
    if 'user_id' not in session:
        return jsonify({'authenticated': False})

    onboarding = get_user_onboarding_status(session['user_id'])
    return jsonify({
        'authenticated': True,
        'user_id': session['user_id'],
        'username': session['username'],
        'is_admin': session.get('is_admin', False),
        'favorite_genres': onboarding.get('favorite_genres', []),
        'rating_count': onboarding.get('rating_count', 0),
        'ratings_needed': onboarding.get('ratings_needed', 10),
        'onboarding_complete': onboarding.get('onboarding_complete', False),
    })


# ── Onboarding ─────────────────────────────────────────────────────────────

@api_bp.route('/onboarding/status', methods=['GET'])
@login_required_api
def onboarding_status():
    return jsonify(get_user_onboarding_status(session['user_id']))


@api_bp.route('/onboarding/genres', methods=['POST'])
@login_required_api
def onboarding_genres():
    data = request.get_json(silent=True) or {}
    genres = data.get('genres', [])

    if not isinstance(genres, list):
        return jsonify({'error': 'Genres must be provided as a list'}), 400

    clean_genres = []
    seen = set()
    for genre in genres:
        value = str(genre).strip()
        if value and value not in seen:
            clean_genres.append(value)
            seen.add(value)

    if not clean_genres:
        return jsonify({'error': 'Select at least one genre'}), 400
    if len(clean_genres) > 8:
        return jsonify({'error': 'Select no more than 8 genres'}), 400

    available_genres = set(get_all_genres())
    invalid = [genre for genre in clean_genres if genre not in available_genres]
    if invalid:
        return jsonify({'error': f'Invalid genre selection: {", ".join(invalid)}'}), 400

    save_favorite_genres(session['user_id'], clean_genres)
    return jsonify(get_user_onboarding_status(session['user_id']))


@api_bp.route('/onboarding/movies', methods=['GET'])
@login_required_api
def onboarding_movies():
    limit = request.args.get('limit', 30, type=int)
    limit = max(10, min(limit, 60))
    movies_list = get_onboarding_movies(session['user_id'], limit=limit)

    for movie in movies_list:
        if movie.get('avg_rating') is not None:
            movie['avg_rating'] = float(movie['avg_rating'])
        if movie.get('user_rating') is not None:
            movie['user_rating'] = float(movie['user_rating'])
        if movie.get('rating_count') is not None:
            movie['rating_count'] = int(movie['rating_count'])
        for key, value in list(movie.items()):
            if hasattr(value, 'isoformat'):
                movie[key] = value.isoformat()

    return jsonify({'movies': movies_list})


@api_bp.route('/onboarding/complete', methods=['POST'])
@login_required_api
def onboarding_complete():
    status = mark_onboarding_complete_if_ready(session['user_id'])

    if not status.get('favorite_genres'):
        return jsonify({'error': 'Select your favorite genres first'}), 400

    if status.get('rating_count', 0) < 10:
        remaining = max(0, 10 - status.get('rating_count', 0))
        return jsonify({
            'error': f'Rate {remaining} more movie(s) to complete onboarding',
            **status,
        }), 400

    return jsonify(status)


# ── Movies ─────────────────────────────────────────────────────────────────

@api_bp.route('/movies')
@login_required_api
def movies():
    page     = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 42, type=int)
    search   = request.args.get('search', '')
    genre    = request.args.get('genre', '')

    movies_list, total = get_movies_paginated(
        page=page, per_page=per_page, search=search, genre=genre
    )

    watchlist_ids = get_watchlist_ids(session['user_id'])
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT movie_id, rating FROM ratings WHERE user_id = %s",
        (session['user_id'],)
    )
    ratings_map = {int(mid): float(r) for mid, r in cursor.fetchall()}
    cursor.close()
    conn.close()

    for m in movies_list:
        m['in_watchlist'] = m['movie_id'] in watchlist_ids
        m['user_rating']  = ratings_map.get(m['movie_id'])
        m['avg_rating']   = float(m['avg_rating']) if m['avg_rating'] else None
        for k, v in m.items():
            if hasattr(v, 'isoformat'):
                m[k] = v.isoformat()

    return jsonify({
        'movies':      movies_list,
        'total':       total,
        'page':        page,
        'per_page':    per_page,
        'total_pages': max(1, (total + per_page - 1) // per_page),
    })


@api_bp.route('/movies/genres')
@login_required_api
def genres():
    return jsonify({'genres': get_all_genres()})


@api_bp.route('/movies/trending')
@login_required_api
def trending():
    limit  = min(request.args.get('limit', 200, type=int), 500)
    genre  = request.args.get('genre', '')
    page   = request.args.get('page', 1, type=int)
    per_page = 42

    all_movies = get_trending_movies(limit=limit)

    if genre:
        all_movies = [m for m in all_movies if genre in (m.get('genres') or '')]

    total       = len(all_movies)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page        = max(1, min(page, total_pages))
    start       = (page - 1) * per_page
    page_movies = all_movies[start:start + per_page]

    watchlist_ids = get_watchlist_ids(session['user_id'])
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT movie_id, rating FROM ratings WHERE user_id = %s",
        (session['user_id'],)
    )
    ratings_map = {int(mid): float(r) for mid, r in cursor.fetchall()}
    cursor.close()
    conn.close()

    for i, m in enumerate(page_movies, start + 1):
        m['rank']         = i
        m['in_watchlist'] = m['movie_id'] in watchlist_ids
        m['user_rating']  = ratings_map.get(m['movie_id'])
        m['avg_rating']   = float(m['avg_rating']) if m['avg_rating'] else None
        for k, v in m.items():
            if hasattr(v, 'isoformat'):
                m[k] = v.isoformat()

    return jsonify({
        'movies':      page_movies,
        'total':       total,
        'page':        page,
        'per_page':    per_page,
        'total_pages': total_pages,
    })


@api_bp.route('/movies/<int:movie_id>', methods=['GET'])
@login_required_api
def movie_detail(movie_id):
    from models.db import get_movie_by_id, get_watchlist_ids

    movie = get_movie_by_id(movie_id)
    if not movie:
        return jsonify({'error': 'Not found'}), 404

    user_id = session['user_id']

    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT rating FROM ratings WHERE user_id=%s AND movie_id=%s", (user_id, movie_id))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    watchlist_ids = get_watchlist_ids(user_id)

    movie['user_rating']  = float(row[0]) if row else None
    movie['in_watchlist'] = movie_id in watchlist_ids
    movie['not_interested'] = movie_id in get_not_interested_ids(user_id)
    movie['avg_rating']   = float(movie['avg_rating']) if movie['avg_rating'] else None

    for k, v in movie.items():
        if hasattr(v, 'isoformat'):
            movie[k] = v.isoformat()

    return jsonify({'movie': movie})


@api_bp.route('/movies/<int:movie_id>/similar', methods=['GET'])
@login_required_api
def similar_movies(movie_id):
    from ml.content_based import get_similar_movies
    from models.db import get_movie_by_id

    limit = max(1, min(request.args.get('limit', 12, type=int), 24))
    excluded = get_not_interested_ids(session['user_id'])
    source_movie = get_movie_by_id(movie_id)
    source_title = (source_movie or {}).get('title', 'this movie')
    source_title = source_title.rsplit(' (', 1)[0]
    source_genres = set(((source_movie or {}).get('genres') or '').split('|'))

    candidates = get_similar_movies(movie_id, n=limit + len(excluded) + 5)
    watchlist_ids = get_watchlist_ids(session['user_id'])

    results = []
    for rec in candidates:
        if rec['movie_id'] in excluded:
            continue
        movie = get_movie_by_id(rec['movie_id'])
        if not movie:
            continue
        movie['similarity_score'] = rec['similarity_score']
        movie['score'] = rec['similarity_score']
        movie['method'] = 'content'
        movie['display_score'] = f"{round(rec['similarity_score'] * 100)}% match"
        movie_genres = set((movie.get('genres') or '').split('|'))
        shared_genres = [g for g in source_genres.intersection(movie_genres) if g and g != '(no genres listed)']
        if shared_genres:
            genre_text = ', '.join(sorted(shared_genres)[:2])
            movie['explanation'] = f"Similar to {source_title} through shared {genre_text} themes and content."
        else:
            movie['explanation'] = f"Recommended because its content profile is similar to {source_title}."
        movie['in_watchlist'] = movie['movie_id'] in watchlist_ids
        movie['avg_rating'] = float(movie['avg_rating']) if movie['avg_rating'] else None
        for key, value in movie.items():
            if hasattr(value, 'isoformat'):
                movie[key] = value.isoformat()
        results.append(movie)
        if len(results) >= limit:
            break
    return jsonify({'movies': results})


@api_bp.route('/feedback/not-interested', methods=['GET'])
@login_required_api
def list_not_interested():
    """Return movies the current user marked as not interested."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT
            m.movie_id, m.title, m.genres, m.poster_url, m.overview,
            m.release_date, m.runtime, m.imdb_rating,
            ni.created_at AS marked_at,
            COUNT(r.id) AS rating_count,
            AVG(r.rating) AS avg_rating
        FROM not_interested ni
        JOIN movies m ON m.movie_id = ni.movie_id
        LEFT JOIN ratings r ON r.movie_id = m.movie_id
        WHERE ni.user_id = %s
        GROUP BY
            m.movie_id, m.title, m.genres, m.poster_url, m.overview,
            m.release_date, m.runtime, m.imdb_rating, ni.created_at
        ORDER BY ni.created_at DESC
    """, (session['user_id'],))
    movies = cursor.fetchall()
    cursor.close()
    conn.close()

    for movie in movies:
        movie['avg_rating'] = float(movie['avg_rating']) if movie['avg_rating'] else None
        movie['imdb_rating'] = float(movie['imdb_rating']) if movie.get('imdb_rating') else None
        movie['not_interested'] = True
        for key, value in movie.items():
            if hasattr(value, 'isoformat'):
                movie[key] = value.isoformat()

    return jsonify({'movies': movies, 'total': len(movies)})


@api_bp.route('/feedback/not-interested', methods=['POST'])
@login_required_api
def mark_not_interested():
    data = request.get_json(silent=True) or {}
    try:
        movie_id = int(data.get('movie_id'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Valid movie_id required'}), 400
    from models.db import get_movie_by_id
    if not get_movie_by_id(movie_id):
        return jsonify({'error': 'Movie not found'}), 404
    add_not_interested(session['user_id'], movie_id)
    remove_from_watchlist(session['user_id'], movie_id)
    return jsonify({'status': 'ok', 'movie_id': movie_id, 'not_interested': True})


@api_bp.route('/feedback/not-interested/remove', methods=['POST'])
@login_required_api
def unmark_not_interested():
    data = request.get_json(silent=True) or {}
    try:
        movie_id = int(data.get('movie_id'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Valid movie_id required'}), 400
    remove_not_interested(session['user_id'], movie_id)
    return jsonify({'status': 'ok', 'movie_id': movie_id, 'not_interested': False})


# ── Ratings ────────────────────────────────────────────────────────────────

@api_bp.route('/rate', methods=['POST'])
@login_required_api
def rate():
    data     = request.get_json()
    movie_id = data.get('movie_id')
    rating   = data.get('rating')

    try:
        movie_id = int(movie_id)
        rating = float(rating)
    except (TypeError, ValueError):
        return jsonify({'error': 'Movie ID and rating must be numeric'}), 400

    if movie_id <= 0 or not (0.5 <= rating <= 5.0) or (rating * 2) % 1 != 0:
        return jsonify({'error': 'Rating must be between 0.5 and 5.0 in 0.5 increments'}), 400

    from models.db import get_movie_by_id
    if not get_movie_by_id(movie_id):
        return jsonify({'error': 'Movie not found'}), 404

    save_rating(session['user_id'], movie_id, rating)
    try:
        import ml.collaborative as cf_module
        cf_module._memory_cache = None
    except Exception:
        pass
    return jsonify({'status': 'ok', 'movie_id': movie_id, 'rating': rating})


@api_bp.route('/ratings')
@login_required_api
def my_ratings():
    ratings = get_user_ratings(session['user_id'])
    for r in ratings:
        for k, v in r.items():
            if hasattr(v, 'isoformat'):
                r[k] = v.isoformat()
    return jsonify({'ratings': ratings})


# ── Watchlist ──────────────────────────────────────────────────────────────

@api_bp.route('/watchlist')
@login_required_api
def watchlist():
    items = get_watchlist(session['user_id'])
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT movie_id, rating FROM ratings WHERE user_id = %s",
        (session['user_id'],)
    )
    ratings_map = {int(mid): float(r) for mid, r in cursor.fetchall()}
    cursor.close()
    conn.close()
    for m in items:
        m['user_rating'] = ratings_map.get(m['movie_id'])
        m['avg_rating']  = float(m['avg_rating']) if m['avg_rating'] else None
        for k, v in m.items():
            if hasattr(v, 'isoformat'):
                m[k] = v.isoformat()
    return jsonify({'watchlist': items})


@api_bp.route('/watchlist/add', methods=['POST'])
@login_required_api
def watchlist_add():
    data = request.get_json()
    movie_id = data.get('movie_id')
    try:
        movie_id = int(movie_id)
    except (TypeError, ValueError):
        return jsonify({'error': 'Valid movie_id required'}), 400
    from models.db import get_movie_by_id
    if not get_movie_by_id(movie_id):
        return jsonify({'error': 'Movie not found'}), 404
    add_to_watchlist(session['user_id'], int(movie_id))
    return jsonify({'status': 'ok', 'action': 'added'})


@api_bp.route('/watchlist/remove', methods=['POST'])
@login_required_api
def watchlist_remove():
    data = request.get_json()
    movie_id = data.get('movie_id')
    if not movie_id:
        return jsonify({'error': 'movie_id required'}), 400
    remove_from_watchlist(session['user_id'], int(movie_id))
    return jsonify({'status': 'ok', 'action': 'removed'})


# ── Recommendations ────────────────────────────────────────────────────────

def format_display_score(rec):
    """Human-readable score label, built from raw (un-normalized) values."""
    method = rec.get('method')
    cf_raw = rec.get('cf_score_raw')
    cb_raw = rec.get('cb_score_raw')
    parts = []
    if method in ('collaborative', 'both') and cf_raw is not None:
        parts.append(f"{cf_raw:.1f}★ predicted")
    if method in ('content', 'both') and cb_raw is not None:
        parts.append(f"{round(cb_raw * 100)}% match")
    return ' · '.join(parts) if parts else None


@api_bp.route('/recommendations')
@login_required_api
def recommendations():
    from ml.collaborative import get_cf_recommendations
    from ml.content_based import get_cb_recommendations
    from ml.hybrid import compute_hybrid_scores
    from models.db import get_movie_by_id, log_recommendations, get_cold_start_movies

    user_id       = session['user_id']
    method_filter = request.args.get('method', 'all')
    page          = request.args.get('page', 1, type=int)
    per_page      = 42

    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM ratings WHERE user_id = %s", (user_id,))
    rating_count = cursor.fetchone()[0]
    cursor.close()
    conn.close()

    if rating_count < 10:
        fallback = get_cold_start_movies(user_id, limit=per_page)
        watchlist_ids = get_watchlist_ids(user_id)
        enriched = []
        for movie in fallback:
            movie['score'] = round(float(movie.pop('fallback_score', 0)), 6)
            movie['method'] = 'fallback'
            movie['explanation'] = movie.pop('fallback_reason', 'Popular among viewers while we learn your taste.')
            movie['in_watchlist'] = movie['movie_id'] in watchlist_ids
            movie['avg_rating'] = float(movie.get('avg_rating') or 0)
            for key, value in movie.items():
                if hasattr(value, 'isoformat'):
                    movie[key] = value.isoformat()
            enriched.append(movie)
        return jsonify({
            'no_ratings': False,
            'is_fallback': True,
            'rating_count': rating_count,
            'ratings_needed': 10 - rating_count,
            'recommendations': enriched,
            'total': len(enriched), 'total_all': len(enriched),
            'page': 1, 'per_page': per_page, 'total_pages': 1,
            'cf_count': 0, 'cb_count': 0, 'method_filter': 'fallback',
        })

    cf_recs = get_cf_recommendations(user_id)
    cb_recs = get_cb_recommendations(user_id)

    # Explicit negative feedback always wins: never recommend these movies again.
    # Filtered here, upstream of the merge, so cf_count/cb_count/total all stay
    # consistent with each other after a "Not Interested" action.
    excluded_ids = get_not_interested_ids(user_id)
    cf_recs = [r for r in cf_recs if r['movie_id'] not in excluded_ids]
    cb_recs = [r for r in cb_recs if r['movie_id'] not in excluded_ids]

    # ── Hybrid merge (weighted: CF 60% + CB 40%, single-signal penalised) ──
    merged = compute_hybrid_scores(cf_recs, cb_recs)
    # merged items have: movie_id, score (hybrid), cf_score, cb_score,
    # cf_score_raw, cb_score_raw, method

    cf_score_map = {r['movie_id']: r['score'] for r in cf_recs}
    cb_score_map = {r['movie_id']: r['score'] for r in cb_recs}

    # ── Method filter ───────────────────────────────────────────────────────
    if method_filter == 'collaborative':
        filtered = [r for r in merged if r['movie_id'] in cf_score_map]
        for r in filtered:
            r['score'] = r['cf_score']
            r['method'] = 'collaborative'
        filtered.sort(key=lambda x: x['score'], reverse=True)

    elif method_filter == 'content':
        filtered = [r for r in merged if r['movie_id'] in cb_score_map]
        for r in filtered:
            r['score'] = r['cb_score']
            r['method'] = 'content'
        filtered.sort(key=lambda x: x['score'], reverse=True)

    else:
        filtered = merged

    total       = len(filtered)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page        = max(1, min(page, total_pages))
    start       = (page - 1) * per_page
    page_recs   = filtered[start:start + per_page]

    # ── Enrich with movie details ───────────────────────────────────────────
    page_ids  = [r['movie_id'] for r in page_recs]
    stats_map = get_movie_ratings_stats(page_ids)

    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT movie_id, rating FROM ratings WHERE user_id = %s", (user_id,)
    )
    ratings_map = {int(mid): float(r) for mid, r in cursor.fetchall()}

    cursor.execute(
        """
        SELECT m.movie_id, m.title, m.genres, r.rating
        FROM ratings r
        JOIN movies m ON m.movie_id = r.movie_id
        WHERE r.user_id = %s AND r.rating >= 3.5
        ORDER BY r.rating DESC, r.timestamp DESC
        LIMIT 20
        """,
        (user_id,),
    )
    liked_movies = [
        {
            'movie_id': int(mid),
            'title': title or 'a movie you liked',
            'genres': {g.strip() for g in (genres or '').split('|') if g.strip()},
            'rating': float(rating),
        }
        for mid, title, genres, rating in cursor.fetchall()
    ]
    cursor.close()
    conn.close()

    def build_explanation(movie, rec):
        """Return a concise label plus evidence shown by the UI."""
        candidate_genres = {
            g.strip() for g in (movie.get('genres') or '').split('|') if g.strip()
        }
        best_match = None
        best_overlap = set()
        for liked in liked_movies:
            overlap = candidate_genres & liked['genres']
            if len(overlap) > len(best_overlap):
                best_match, best_overlap = liked, overlap
            elif len(overlap) == len(best_overlap) and overlap and best_match:
                if liked['rating'] > best_match['rating']:
                    best_match, best_overlap = liked, overlap

        method = rec.get('method')
        details = []
        if method in ('collaborative', 'both'):
            details.append(
                'Collaborative filtering found this movie from rating patterns '
                'learned from users with preferences similar to yours.'
            )
        if method in ('content', 'both'):
            if best_match and best_overlap:
                shared = ', '.join(sorted(best_overlap)[:3])
                details.append(
                    f"It shares {shared} with {best_match['title']}, which you rated "
                    f"{best_match['rating']:g}★."
                )
            else:
                details.append(
                    'Its title and genre features are similar to movies you rated positively.'
                )

        if method == 'both':
            title = 'Supported by both recommendation methods'
            summary = (
                f"Because you liked {best_match['title']} and similar users also liked this."
                if best_match else
                'Matches your movie preferences and similar users’ rating patterns.'
            )
        elif method == 'content':
            title = 'Similar to movies you liked'
            summary = (
                f"Because you rated {best_match['title']} {best_match['rating']:g}★."
                if best_match else
                'Matches the genres and features of movies you rated positively.'
            )
        else:
            title = 'Popular with users like you'
            summary = 'Users with rating patterns similar to yours also liked this movie.'

        return {
            'explanation': summary,
            'explanation_title': title,
            'explanation_details': details,
            'explanation_method': method or 'recommendation',
        }

    enriched = []
    for rec in page_recs:
        movie = get_movie_by_id(rec['movie_id'])
        if not movie:
            continue
        stats = stats_map.get(movie['movie_id'], {})
        explanation_data = build_explanation(movie, rec)
        entry = {
            **movie,
            **rec,
            **explanation_data,
            'display_score': None if method_filter == 'all' else format_display_score(rec),
            'avg_rating':   float(stats.get('avg_rating') or 0),
            'rating_count': stats.get('rating_count', 0),
            'user_rating':  ratings_map.get(movie['movie_id']),
        }
        for k, v in entry.items():
            if hasattr(v, 'isoformat'):
                entry[k] = v.isoformat()
        enriched.append(entry)

    if page == 1 and method_filter == 'all':
        log_recommendations(user_id, merged[:25])

    return jsonify({
        'no_ratings':      False,
        'rating_count':    rating_count,
        'recommendations': enriched,
        'total':           total,
        'total_all':       len(merged),
        'page':            page,
        'per_page':        per_page,
        'total_pages':     total_pages,
        'cf_count':        len(cf_score_map),
        'cb_count':        len(cb_score_map),
        'method_filter':   method_filter,
        'is_fallback':     False,
        'hybrid_weights':  {'collaborative': __import__('ml.hybrid', fromlist=['CF_WEIGHT']).CF_WEIGHT, 'content_based': __import__('ml.hybrid', fromlist=['CB_WEIGHT']).CB_WEIGHT},
    })


# ── Profile ────────────────────────────────────────────────────────────────

@api_bp.route('/profile')
@login_required_api
def profile():
    ratings   = get_user_ratings(session['user_id'])
    watchlist = get_watchlist(session['user_id'])
    for r in ratings:
        for k, v in r.items():
            if hasattr(v, 'isoformat'): r[k] = v.isoformat()
    for w in watchlist:
        w['avg_rating'] = float(w['avg_rating']) if w['avg_rating'] else None
        for k, v in w.items():
            if hasattr(v, 'isoformat'): w[k] = v.isoformat()
    avg = (sum(r['rating'] for r in ratings) / len(ratings)) if ratings else None
    return jsonify({
        'username':  session['username'],
        'ratings':   ratings,
        'watchlist': watchlist,
        'avg_rating': round(avg, 1) if avg else None,
    })