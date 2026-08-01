import mysql.connector
import numpy as np
from config import DB_CONFIG


def get_connection():
    return mysql.connector.connect(**DB_CONFIG)


def get_movies_paginated(page=1, per_page=20, search='', genre=''):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    offset = (page - 1) * per_page

    conditions = []
    params = []
    if search:
        conditions.append("title LIKE %s")
        params.append(f'%{search}%')
    if genre:
        conditions.append("genres LIKE %s")
        params.append(f'%{genre}%')

    where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''

    # Join ratings to get avg and count per movie
    cursor.execute(f"""
        SELECT m.*,
               COUNT(r.id)    AS rating_count,
               AVG(r.rating)  AS avg_rating
        FROM movies m
        LEFT JOIN ratings r ON m.movie_id = r.movie_id
        {where}
        GROUP BY m.movie_id
        LIMIT %s OFFSET %s
    """, params + [per_page, offset])
    movies = cursor.fetchall()

    cursor.execute(f"SELECT COUNT(*) as cnt FROM movies {where}", params)
    total = cursor.fetchone()['cnt']

    cursor.close()
    conn.close()
    return movies, total


def get_movie_by_id(movie_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT m.*,
               COUNT(r.id)   AS rating_count,
               AVG(r.rating) AS avg_rating
        FROM movies m
        LEFT JOIN ratings r ON m.movie_id = r.movie_id
        WHERE m.movie_id = %s
        GROUP BY m.movie_id
    """, (movie_id,))
    movie = cursor.fetchone()
    cursor.close()
    conn.close()
    return movie


def get_all_genres(conn=None):
    close = conn is None
    if conn is None:
        conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT genres FROM movies WHERE genres IS NOT NULL")
    rows = cursor.fetchall()
    cursor.close()
    if close:
        conn.close()
    genre_set = set()
    for (g,) in rows:
        if g:
            for part in g.split('|'):
                genre_set.add(part.strip())
    return sorted(genre_set)


def get_trending_movies(limit=200):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT m.*, COUNT(r.id) AS rating_count, AVG(r.rating) AS avg_rating
        FROM movies m
        JOIN ratings r ON m.movie_id = r.movie_id
        GROUP BY m.movie_id
        ORDER BY rating_count DESC, avg_rating DESC
        LIMIT %s
    """, (limit,))
    movies = cursor.fetchall()
    cursor.close()
    conn.close()
    return movies


import time

def save_rating(user_id, movie_id, rating):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO ratings (user_id, movie_id, rating, timestamp)
           VALUES (%s, %s, %s, %s)
           ON DUPLICATE KEY UPDATE rating = %s, timestamp = %s""",
        (user_id, movie_id, rating, int(time.time()), rating, int(time.time()))
    )
    conn.commit()
    cursor.close()
    conn.close()


def get_user_ratings(user_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT r.movie_id, m.title, m.genres, m.poster_url, m.overview, r.rating
        FROM ratings r
        JOIN movies m ON r.movie_id = m.movie_id
        WHERE r.user_id = %s
        ORDER BY r.rating DESC
    """, (user_id,))
    ratings = cursor.fetchall()
    cursor.close()
    conn.close()
    return ratings


def add_to_watchlist(user_id, movie_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT IGNORE INTO watchlist (user_id, movie_id) VALUES (%s, %s)",
        (user_id, movie_id)
    )
    conn.commit()
    cursor.close()
    conn.close()


def remove_from_watchlist(user_id, movie_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM watchlist WHERE user_id=%s AND movie_id=%s",
        (user_id, movie_id)
    )
    conn.commit()
    cursor.close()
    conn.close()


def get_watchlist(user_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT m.*,
               COUNT(r.id)   AS rating_count,
               AVG(r.rating) AS avg_rating,
               w.added_at
        FROM watchlist w
        JOIN movies m ON w.movie_id = m.movie_id
        LEFT JOIN ratings r ON m.movie_id = r.movie_id
        WHERE w.user_id = %s
        GROUP BY m.movie_id, w.added_at
        ORDER BY w.added_at DESC
    """, (user_id,))
    items = cursor.fetchall()
    cursor.close()
    conn.close()
    return items


def get_watchlist_ids(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT movie_id FROM watchlist WHERE user_id=%s", (user_id,))
    ids = {row[0] for row in cursor.fetchall()}
    cursor.close()
    conn.close()
    return ids


def get_movie_ratings_stats(movie_ids):
    """Return {movie_id: {avg_rating, rating_count}} for a list of ids."""
    if not movie_ids:
        return {}
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    placeholders = ','.join(['%s'] * len(movie_ids))
    cursor.execute(f"""
        SELECT movie_id,
               COUNT(id)    AS rating_count,
               AVG(rating)  AS avg_rating
        FROM ratings
        WHERE movie_id IN ({placeholders})
        GROUP BY movie_id
    """, list(movie_ids))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return {r['movie_id']: r for r in rows}


def log_recommendations(user_id, recommendations):
    if not recommendations:
        return
    conn = get_connection()
    cursor = conn.cursor()

    movie_ids = [rec['movie_id'] for rec in recommendations]
    placeholders = ','.join(['%s'] * len(movie_ids))
    cursor.execute(f"""
        SELECT movie_id FROM recommendation_logs
        WHERE user_id = %s
          AND movie_id IN ({placeholders})
          AND created_at >= NOW() - INTERVAL 24 HOUR
    """, [user_id] + movie_ids)
    already_logged = {row[0] for row in cursor.fetchall()}

    to_insert = [
        (user_id, rec['movie_id'], rec['score'], rec['method'])
        for rec in recommendations
        if rec['movie_id'] not in already_logged
    ]

    if to_insert:
        cursor.executemany(
            "INSERT INTO recommendation_logs (user_id, movie_id, score, method) VALUES (%s,%s,%s,%s)",
            to_insert
        )
        conn.commit()
    cursor.close()
    conn.close()


def get_cold_start_movies(user_id, limit=84):
    """Popularity fallback with a genre boost from any ratings the user already has."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT r.movie_id, rating, genres FROM ratings r JOIN movies m ON m.movie_id=r.movie_id WHERE r.user_id=%s", (user_id,))
    rows = cursor.fetchall()
    seen = {int(r['movie_id']) for r in rows}
    cursor.execute("SELECT movie_id FROM not_interested WHERE user_id=%s", (user_id,))
    seen.update(int(row[0]) for row in cursor.fetchall())
    genre_scores = {}
    for row in rows:
        weight = max(float(row['rating']) - 2.5, 0.0)
        for genre in (row.get('genres') or '').split('|'):
            genre = genre.strip()
            if genre:
                genre_scores[genre] = genre_scores.get(genre, 0.0) + weight

    cursor.execute("""
        SELECT m.*, COUNT(r.id) AS rating_count, AVG(r.rating) AS avg_rating
        FROM movies m JOIN ratings r ON r.movie_id=m.movie_id
        GROUP BY m.movie_id
        HAVING COUNT(r.id) >= 3
        ORDER BY (AVG(r.rating) * LOG10(COUNT(r.id)+1)) DESC
        LIMIT 500
    """)
    candidates = cursor.fetchall()
    cursor.close(); conn.close()
    ranked=[]
    for m in candidates:
        if int(m['movie_id']) in seen:
            continue
        popularity = float(m.get('avg_rating') or 0) * np.log10(float(m.get('rating_count') or 0)+1)
        boost = sum(genre_scores.get(g.strip(),0.0) for g in (m.get('genres') or '').split('|'))
        m['fallback_score'] = popularity + 0.15*boost
        m['fallback_reason'] = 'Popular among viewers' if not genre_scores else 'Popular and related to genres you rated'
        ranked.append(m)
    ranked.sort(key=lambda x:x['fallback_score'], reverse=True)
    return ranked[:limit]


def get_user_onboarding_status(user_id):
    """Return favorite genres, rating count, and whether onboarding is complete."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT favorite_genres, completed_at FROM user_preferences WHERE user_id=%s", (user_id,))
    pref = cursor.fetchone() or {}
    cursor.execute("SELECT COUNT(*) AS cnt FROM ratings WHERE user_id=%s", (user_id,))
    rating_count = int(cursor.fetchone()['cnt'])
    cursor.close(); conn.close()
    favorite_genres = [g for g in (pref.get('favorite_genres') or '').split('|') if g]
    return {
        'favorite_genres': favorite_genres,
        'rating_count': rating_count,
        'ratings_needed': max(0, 10 - rating_count),
        'onboarding_complete': bool(pref.get('completed_at')) and rating_count >= 10,
    }


def save_favorite_genres(user_id, genres):
    clean = sorted({str(g).strip() for g in genres if str(g).strip()})
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_preferences (user_id, favorite_genres)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE favorite_genres=VALUES(favorite_genres)
    """, (user_id, '|'.join(clean)))
    conn.commit(); cursor.close(); conn.close()
    return clean


def mark_onboarding_complete_if_ready(user_id):
    status = get_user_onboarding_status(user_id)
    if status['favorite_genres'] and status['rating_count'] >= 10:
        conn = get_connection(); cursor = conn.cursor()
        cursor.execute("UPDATE user_preferences SET completed_at=COALESCE(completed_at, CURRENT_TIMESTAMP) WHERE user_id=%s", (user_id,))
        conn.commit(); cursor.close(); conn.close()
        status['onboarding_complete'] = True
    return status


def get_onboarding_movies(user_id, limit=30):
    """Popular, diverse starter movies selected from the user's chosen genres."""
    status = get_user_onboarding_status(user_id)
    genres = status['favorite_genres']
    conn = get_connection(); cursor = conn.cursor(dictionary=True)
    params = []
    where = ''
    if genres:
        clauses = []
        for genre in genres:
            clauses.append("m.genres LIKE %s")
            params.append(f'%{genre}%')
        where = 'WHERE (' + ' OR '.join(clauses) + ')'
    cursor.execute(f"""
        SELECT m.*, COUNT(r.id) AS rating_count, AVG(r.rating) AS avg_rating
        FROM movies m
        LEFT JOIN ratings r ON r.movie_id=m.movie_id
        {where}
        GROUP BY m.movie_id
        HAVING COUNT(r.id) >= 3
        ORDER BY (AVG(r.rating) * LOG10(COUNT(r.id)+1)) DESC
        LIMIT %s
    """, params + [max(limit * 3, 60)])
    candidates = cursor.fetchall()
    cursor.execute("SELECT movie_id, rating FROM ratings WHERE user_id=%s", (user_id,))
    rated = {
        int(row['movie_id']): float(row['rating'])
        for row in cursor.fetchall()
    }
    cursor.close(); conn.close()

    # Encourage variety by round-robin over primary genres.
    buckets = {g: [] for g in genres}
    other = []
    for movie in candidates:
        movie['avg_rating'] = float(movie.get('avg_rating') or 0)
        movie['user_rating'] = rated.get(int(movie['movie_id']))
        matched = False
        for genre in genres:
            if genre in (movie.get('genres') or '').split('|'):
                buckets[genre].append(movie); matched = True; break
        if not matched: other.append(movie)
    selected = []
    while len(selected) < limit and any(buckets.values()):
        for genre in genres:
            if buckets.get(genre) and len(selected) < limit:
                movie = buckets[genre].pop(0)
                if movie not in selected: selected.append(movie)
    for movie in candidates:
        if len(selected) >= limit: break
        if movie not in selected: selected.append(movie)
    return selected[:limit]


# ── Explicit recommendation feedback ─────────────────────────────────────

def add_not_interested(user_id, movie_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT IGNORE INTO not_interested (user_id, movie_id) VALUES (%s, %s)",
        (user_id, movie_id),
    )
    conn.commit()
    cursor.close()
    conn.close()


def remove_not_interested(user_id, movie_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM not_interested WHERE user_id=%s AND movie_id=%s",
        (user_id, movie_id),
    )
    conn.commit()
    cursor.close()
    conn.close()


def get_not_interested_ids(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT movie_id FROM not_interested WHERE user_id=%s", (user_id,))
    ids = {int(row[0]) for row in cursor.fetchall()}
    cursor.close()
    conn.close()
    return ids
