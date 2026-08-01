from functools import wraps
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Lock

from flask import Blueprint, jsonify, request, session
from models.db import get_connection
import ml.collaborative as cf_module
import ml.content_based as cb_module
from ml.evaluation import evaluate_movielens, save_results

admin_api_bp = Blueprint('admin_api', __name__, url_prefix='/api/admin')
_evaluation_lock = Lock()


def admin_required_api(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        conn   = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT is_admin FROM users WHERE user_id = %s", (session['user_id'],))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        if not user or not user.get('is_admin'):
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated


# ── Dashboard stats ────────────────────────────────────────────────────────

@admin_api_bp.route('/stats')
@admin_required_api
def stats():
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS cnt FROM users WHERE password_hash != 'ml_placeholder'")
    total_users = cursor.fetchone()['cnt']

    cursor.execute("SELECT COUNT(*) AS cnt FROM movies")
    total_movies = cursor.fetchone()['cnt']

    cursor.execute("""
        SELECT COUNT(*) AS cnt FROM ratings
        WHERE user_id NOT IN (SELECT user_id FROM users WHERE password_hash='ml_placeholder')
    """)
    total_ratings = cursor.fetchone()['cnt']

    cursor.execute("SELECT COUNT(*) AS cnt FROM users WHERE is_banned = 1")
    banned_users = cursor.fetchone()['cnt']

    cursor.execute("SELECT COUNT(*) AS cnt FROM users WHERE is_admin = 1")
    admin_users = cursor.fetchone()['cnt']

    cursor.execute("""
        SELECT DATE(FROM_UNIXTIME(timestamp)) AS day, COUNT(*) AS cnt
        FROM ratings
        WHERE timestamp IS NOT NULL
          AND timestamp > UNIX_TIMESTAMP(NOW() - INTERVAL 14 DAY)
          AND user_id NOT IN (SELECT user_id FROM users WHERE password_hash='ml_placeholder')
        GROUP BY day ORDER BY day
    """)
    ratings_by_day = [{'day': str(r['day']), 'cnt': r['cnt']} for r in cursor.fetchall()]

    cursor.execute("""
        SELECT m.title, COUNT(r.id) AS cnt, AVG(r.rating) AS avg_r
        FROM ratings r JOIN movies m ON r.movie_id = m.movie_id
        GROUP BY r.movie_id ORDER BY cnt DESC LIMIT 8
    """)
    top_movies = [{'title': r['title'], 'cnt': r['cnt'], 'avg_r': float(r['avg_r'] or 0)} for r in cursor.fetchall()]

    cursor.execute("SELECT genres FROM movies WHERE genres IS NOT NULL")
    genre_counts = {}
    for row in cursor.fetchall():
        for g in (row['genres'] or '').split('|'):
            g = g.strip()
            if g and g != '(no genres listed)':
                genre_counts[g] = genre_counts.get(g, 0) + 1
    top_genres = [{'genre': k, 'cnt': v} for k, v in sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:12]]

    cursor.execute("SELECT FLOOR(rating) AS star, COUNT(*) AS cnt FROM ratings GROUP BY star ORDER BY star")
    rating_dist = [{'star': r['star'], 'cnt': r['cnt']} for r in cursor.fetchall()]

    # Support both the older ml_cache schema (without built_by)
    # and the newer schema (with built_by).
    cursor.execute("SHOW COLUMNS FROM ml_cache LIKE 'built_by'")
    has_built_by = cursor.fetchone() is not None

    if has_built_by:
        cursor.execute("""
            SELECT mc.cache_key, mc.data_hash, mc.built_at,
                   LENGTH(mc.model_blob) AS blob_size,
                   u.username AS built_by
            FROM ml_cache mc
            LEFT JOIN users u ON mc.built_by = u.user_id
        """)
    else:
        cursor.execute("""
            SELECT mc.cache_key, mc.data_hash, mc.built_at,
                   LENGTH(mc.model_blob) AS blob_size,
                   NULL AS built_by
            FROM ml_cache mc
        """)

    cache_rows = [
        {
            'cache_key': r['cache_key'],
            'data_hash': r['data_hash'],
            'built_at': str(r['built_at']) if r['built_at'] else None,
            'blob_size': r['blob_size'] or 0,
            'built_by': r['built_by'] or 'auto',
        }
        for r in cursor.fetchall()
    ]

    cursor.close()
    conn.close()

    return jsonify({
        'total_users':   total_users,
        'total_movies':  total_movies,
        'total_ratings': total_ratings,
        'banned_users':  banned_users,
        'admin_users':   admin_users,
        'ratings_by_day': ratings_by_day,
        'top_movies':    top_movies,
        'top_genres':    top_genres,
        'rating_dist':   rating_dist,
        'cache_rows':    cache_rows,
    })


@admin_api_bp.route('/user-growth')
@admin_required_api
def user_growth():
    """Daily new user registrations over the last 60 days."""
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT
            DATE(created_at)  AS day,
            COUNT(*)          AS new_users,
            SUM(COUNT(*)) OVER (ORDER BY DATE(created_at)) AS cumulative
        FROM users
        WHERE password_hash != 'ml_placeholder'
          AND created_at >= NOW() - INTERVAL 60 DAY
        GROUP BY DATE(created_at)
        ORDER BY day
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify({
        'growth': [{'day': str(r['day']), 'new_users': r['new_users'], 'cumulative': r['cumulative']}
                   for r in rows]
    })


@admin_api_bp.route('/rec-accuracy')
@admin_required_api
def rec_accuracy():
    """
    Recommendation accuracy: for each logged recommendation,
    check whether the user later rated that movie, and if so,
    whether they rated it highly (>= 3.5).

    Returns:
      - total_logged      : total recommendation events logged
      - rated_count       : how many were later rated by the user
      - highly_rated      : how many were rated >= 3.5
      - accuracy_pct      : highly_rated / rated_count * 100
      - rated_pct         : rated_count / total_logged * 100
      - by_method         : breakdown per recommendation method
      - score_correlation : avg rec score vs avg user rating buckets
    """
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Overall counts
    cursor.execute("""
        SELECT
            COUNT(*)                                         AS total_logged,
            SUM(r.rating IS NOT NULL)                        AS rated_count,
            SUM(r.rating >= 3.5)                             AS highly_rated,
            AVG(r.rating)                                    AS avg_user_rating
        FROM recommendation_logs rl
        LEFT JOIN ratings r
               ON r.user_id  = rl.user_id
              AND r.movie_id = rl.movie_id
        WHERE rl.user_id NOT IN (
            SELECT user_id FROM users WHERE password_hash = 'ml_placeholder'
        )
    """)
    overall = cursor.fetchone()

    # Per-method breakdown
    cursor.execute("""
        SELECT
            rl.method,
            COUNT(*)                  AS total,
            SUM(r.rating IS NOT NULL) AS rated,
            SUM(r.rating >= 3.5)      AS highly_rated,
            AVG(r.rating)             AS avg_rating
        FROM recommendation_logs rl
        LEFT JOIN ratings r
               ON r.user_id  = rl.user_id
              AND r.movie_id = rl.movie_id
        WHERE rl.user_id NOT IN (
            SELECT user_id FROM users WHERE password_hash = 'ml_placeholder'
        )
        GROUP BY rl.method
    """)
    by_method = cursor.fetchall()

    # Score buckets: group rec scores into 0.1-wide bins, show avg user rating per bin
    cursor.execute("""
        SELECT
            ROUND(rl.score, 1)   AS score_bucket,
            COUNT(*)             AS count,
            AVG(r.rating)        AS avg_user_rating
        FROM recommendation_logs rl
        JOIN ratings r
          ON r.user_id  = rl.user_id
         AND r.movie_id = rl.movie_id
        WHERE rl.score IS NOT NULL
          AND rl.user_id NOT IN (
              SELECT user_id FROM users WHERE password_hash = 'ml_placeholder'
          )
        GROUP BY ROUND(rl.score, 1)
        ORDER BY score_bucket
    """)
    buckets = cursor.fetchall()

    # Accuracy over time (weekly)
    cursor.execute("""
        SELECT
            DATE(rl.created_at) - INTERVAL DAYOFWEEK(DATE(rl.created_at))-1 DAY AS week_start,
            COUNT(*)                  AS total,
            SUM(r.rating >= 3.5)      AS highly_rated
        FROM recommendation_logs rl
        LEFT JOIN ratings r
               ON r.user_id  = rl.user_id
              AND r.movie_id = rl.movie_id
        WHERE rl.created_at >= NOW() - INTERVAL 12 WEEK
          AND rl.user_id NOT IN (
              SELECT user_id FROM users WHERE password_hash = 'ml_placeholder'
          )
        GROUP BY week_start
        ORDER BY week_start
    """)
    weekly = cursor.fetchall()

    cursor.close()
    conn.close()

    total    = overall['total_logged'] or 0
    rated    = int(overall['rated_count'] or 0)
    highly   = int(overall['highly_rated'] or 0)

    return jsonify({
        'total_logged':   total,
        'rated_count':    rated,
        'highly_rated':   highly,
        'accuracy_pct':   round(highly / rated * 100, 1) if rated else 0,
        'rated_pct':      round(rated  / total * 100, 1) if total else 0,
        'avg_user_rating': round(float(overall['avg_user_rating'] or 0), 2),
        'by_method': [
            {
                'method':      r['method'],
                'total':       r['total'],
                'rated':       int(r['rated'] or 0),
                'highly_rated':int(r['highly_rated'] or 0),
                'accuracy_pct':round(int(r['highly_rated'] or 0) / int(r['rated'] or 1) * 100, 1),
                'avg_rating':  round(float(r['avg_rating'] or 0), 2),
            }
            for r in by_method
        ],
        'score_buckets': [
            {
                'score':          float(r['score_bucket'] or 0),
                'count':          r['count'],
                'avg_user_rating':round(float(r['avg_user_rating'] or 0), 2),
            }
            for r in buckets
        ],
        'weekly_accuracy': [
            {
                'week':       str(r['week_start']),
                'total':      r['total'],
                'highly_rated': int(r['highly_rated'] or 0),
                'pct':        round(int(r['highly_rated'] or 0) / r['total'] * 100, 1) if r['total'] else 0,
            }
            for r in weekly
        ],
    })


# ── Users ──────────────────────────────────────────────────────────────────

@admin_api_bp.route('/users')
@admin_required_api
def users():
    search    = request.args.get('search', '')
    page      = request.args.get('page', 1, type=int)
    per_page  = 20
    offset    = (page - 1) * per_page

    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)

    where  = "WHERE u.password_hash != 'ml_placeholder'"
    params = []
    if search:
        where += " AND (u.username LIKE %s OR u.email LIKE %s)"
        params += [f'%{search}%', f'%{search}%']

    cursor.execute(f"""
        SELECT u.user_id, u.username, u.email, u.is_admin, u.is_banned,
               u.created_at, COUNT(r.id) AS rating_count
        FROM users u
        LEFT JOIN ratings r ON u.user_id = r.user_id
        {where}
        GROUP BY u.user_id
        ORDER BY u.created_at DESC
        LIMIT %s OFFSET %s
    """, params + [per_page, offset])
    user_list = cursor.fetchall()

    cursor.execute(f"SELECT COUNT(*) AS cnt FROM users u {where}", params)
    total = cursor.fetchone()['cnt']
    cursor.close()
    conn.close()

    for u in user_list:
        u['created_at'] = str(u['created_at']) if u['created_at'] else None
        u['is_admin']   = bool(u['is_admin'])
        u['is_banned']  = bool(u['is_banned'])

    return jsonify({
        'users':       user_list,
        'total':       total,
        'page':        page,
        'total_pages': max(1, (total + per_page - 1) // per_page),
    })


@admin_api_bp.route('/users/<int:user_id>/ban', methods=['POST'])
@admin_required_api
def ban_user(user_id):
    if user_id == session['user_id']:
        return jsonify({'error': 'Cannot ban yourself'}), 400
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_banned = NOT is_banned WHERE user_id = %s", (user_id,))
    conn.commit()
    cursor.execute("SELECT is_banned FROM users WHERE user_id = %s", (user_id,))
    banned = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return jsonify({'banned': bool(banned)})


@admin_api_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@admin_required_api
def delete_user(user_id):
    if user_id == session['user_id']:
        return jsonify({'error': 'Cannot delete yourself'}), 400
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM ratings             WHERE user_id = %s", (user_id,))
    cursor.execute("DELETE FROM watchlist           WHERE user_id = %s", (user_id,))
    cursor.execute("DELETE FROM recommendation_logs WHERE user_id = %s", (user_id,))
    cursor.execute("DELETE FROM users               WHERE user_id = %s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'deleted': True})


@admin_api_bp.route('/users/<int:user_id>/toggle_admin', methods=['POST'])
@admin_required_api
def toggle_admin(user_id):
    if user_id == session['user_id']:
        return jsonify({'error': 'Cannot change your own admin status'}), 400
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_admin = NOT is_admin WHERE user_id = %s", (user_id,))
    conn.commit()
    cursor.execute("SELECT is_admin FROM users WHERE user_id = %s", (user_id,))
    is_admin = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return jsonify({'is_admin': bool(is_admin)})


# ── Movies ─────────────────────────────────────────────────────────────────

@admin_api_bp.route('/movies')
@admin_required_api
def movies():
    search   = request.args.get('search', '')
    page     = request.args.get('page', 1, type=int)
    per_page = 20
    offset   = (page - 1) * per_page

    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)

    where  = ''
    params = []
    if search:
        where  = 'WHERE m.title LIKE %s OR m.genres LIKE %s'
        params = [f'%{search}%', f'%{search}%']

    cursor.execute(f"""
        SELECT m.movie_id, m.title, m.genres, m.poster_url, m.overview,
               COUNT(r.id) AS rating_count, AVG(r.rating) AS avg_rating
        FROM movies m
        LEFT JOIN ratings r ON m.movie_id = r.movie_id
        {where}
        GROUP BY m.movie_id
        ORDER BY m.movie_id DESC
        LIMIT %s OFFSET %s
    """, params + [per_page, offset])
    movie_list = cursor.fetchall()

    cursor.execute(f"SELECT COUNT(*) AS cnt FROM movies m {where}", params)
    total = cursor.fetchone()['cnt']
    cursor.close()
    conn.close()

    for m in movie_list:
        m['avg_rating'] = float(m['avg_rating']) if m['avg_rating'] else None

    return jsonify({
        'movies':      movie_list,
        'total':       total,
        'page':        page,
        'total_pages': max(1, (total + per_page - 1) // per_page),
    })


@admin_api_bp.route('/movies/add', methods=['POST'])
@admin_required_api
def add_movie():
    data = request.get_json()
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO movies (movie_id, title, genres, poster_url, overview)
            VALUES (%s, %s, %s, %s, %s)
        """, (data['movie_id'], data['title'], data.get('genres', ''),
              data.get('poster_url'), data.get('overview')))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        cursor.close()
        conn.close()
        return jsonify({'error': str(e)}), 400


@admin_api_bp.route('/movies/<int:movie_id>/edit', methods=['POST'])
@admin_required_api
def edit_movie(movie_id):
    data = request.get_json()
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE movies SET title=%s, genres=%s, poster_url=%s, overview=%s
        WHERE movie_id=%s
    """, (data['title'], data.get('genres', ''),
          data.get('poster_url'), data.get('overview'), movie_id))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True})


@admin_api_bp.route('/movies/<int:movie_id>/delete', methods=['POST'])
@admin_required_api
def delete_movie(movie_id):
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM ratings             WHERE movie_id = %s", (movie_id,))
    cursor.execute("DELETE FROM watchlist           WHERE movie_id = %s", (movie_id,))
    cursor.execute("DELETE FROM recommendation_logs WHERE movie_id = %s", (movie_id,))
    cursor.execute("DELETE FROM movies              WHERE movie_id = %s", (movie_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'deleted': True})


# ── Rec logs ───────────────────────────────────────────────────────────────

@admin_api_bp.route('/rec-logs')
@admin_required_api
def rec_logs():
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT rl.user_id, u.username, m.title, rl.score, rl.method, rl.created_at
        FROM recommendation_logs rl
        JOIN users  u ON rl.user_id  = u.user_id
        JOIN movies m ON rl.movie_id = m.movie_id
        ORDER BY rl.created_at DESC LIMIT 20
    """)
    logs = cursor.fetchall()
    cursor.close()
    conn.close()
    for l in logs:
        l['created_at'] = str(l['created_at'])
    return jsonify({'logs': logs})


# ── Cache ──────────────────────────────────────────────────────────────────

@admin_api_bp.route('/cache/clear', methods=['POST'])
@admin_required_api
def clear_cache():
    key    = request.json.get('key')
    conn   = get_connection()
    cursor = conn.cursor()
    if key:
        cursor.execute("DELETE FROM ml_cache WHERE cache_key = %s", (key,))
    else:
        cursor.execute("DELETE FROM ml_cache")
    conn.commit()
    cursor.close()
    conn.close()
    cf_module._memory_cache = None
    cb_module._memory_cache = None
    return jsonify({'success': True})


@admin_api_bp.route('/cache/rebuild', methods=['POST'])
@admin_required_api
def rebuild_cache():
    key      = request.json.get('key', 'all')
    built_by = session['user_id']
    try:
        if key in ('svd_model', 'all'):
            cf_module._memory_cache = None
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM ml_cache WHERE cache_key = 'svd_model'")
            conn.commit(); cursor.close(); conn.close()
            cf_module.get_or_build_model(built_by=built_by)
        if key in ('cb_model', 'all'):
            cb_module._memory_cache = None
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM ml_cache WHERE cache_key = 'cb_model'")
            conn.commit();
            cursor.close();
            conn.close()
            cb_module.get_or_build_model(built_by=built_by)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _evaluation_paths():
    root = Path(__file__).resolve().parents[1]
    return root, root / 'evaluation_results.json'


@admin_api_bp.route('/offline-evaluation')
@admin_required_api
def offline_evaluation():
    """Return the most recently saved Precision@K/Recall@K evaluation (MovieLens baseline)."""
    _, results_path = _evaluation_paths()
    if not results_path.exists():
        return jsonify({
            'error': 'No saved evaluation is available yet. Click Run Evaluation.'
        }), 404
    try:
        return jsonify(json.loads(results_path.read_text(encoding='utf-8')))
    except (OSError, json.JSONDecodeError):
        return jsonify({'error': 'Evaluation results could not be read.'}), 500


@admin_api_bp.route('/offline-evaluation/run', methods=['POST'])
@admin_required_api
def run_offline_evaluation():
    """Run a fresh leakage-free evaluation and save its results for the admin page."""
    if not _evaluation_lock.acquire(blocking=False):
        return jsonify({'error': 'An evaluation is already running.'}), 409

    try:
        root, results_path = _evaluation_paths()
        payload = request.get_json(silent=True) or {}

        # Keep limits conservative so the action is practical during a local demo.
        k = max(1, min(int(payload.get('k', 10)), 50))
        max_users = max(10, min(int(payload.get('max_users', 200)), 610))
        random_state = int(payload.get('random_state', 42))

        results = evaluate_movielens(
            k=k,
            max_users=max_users,
            random_state=random_state,
        )
        results['generated_at'] = datetime.now(timezone.utc).isoformat()
        results['generated_by_user_id'] = session['user_id']
        save_results(results, results_path)
        return jsonify(results)
    except (OSError, ValueError, TypeError) as exc:
        return jsonify({'error': f'Evaluation failed: {exc}'}), 400
    except Exception:
        # Avoid exposing internal paths or stack traces to the browser.
        return jsonify({'error': 'Evaluation failed because of an internal error.'}), 500
    finally:
        _evaluation_lock.release()

