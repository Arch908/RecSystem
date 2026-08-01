"""
Fast parallel TMDB fetcher.
Fetches: poster, overview, trailer (YouTube), cast, director,
         runtime, release_date, language, imdb_rating.

Usage:
    python fetch_tmdb.py              # fetch everything missing
    python fetch_tmdb.py --details    # re-fetch only details (runtime, release, etc.)
    python fetch_tmdb.py --media      # re-fetch only trailer + cast
"""

import re
import sys
import time
import argparse
import requests
import mysql.connector
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

try:
    from config import DB_CONFIG, TMDB_API_KEY
except ImportError:
    print("ERROR: Could not import config.py. Run from your project root folder.")
    sys.exit(1)

if not TMDB_API_KEY or TMDB_API_KEY == 'your_tmdb_api_key_here':
    print("ERROR: Please set TMDB_API_KEY in config.py")
    sys.exit(1)

POSTER_BASE = 'https://image.tmdb.org/t/p/w342'
BASE_URL    = 'https://api.themoviedb.org/3'
MAX_WORKERS = 10
BATCH_SIZE  = 50

db_lock = Lock()


# ── Title helpers ──────────────────────────────────────────────────────────

def extract_year(title):
    m = re.search(r'\((\d{4})\)$', title.strip())
    return m.group(1) if m else None

def remove_year_suffix(title):
    return re.sub(r'\s*\(\d{4}\)\s*$', '', title).strip()

def remove_all_years(title):
    t = re.sub(r'\s*\(\d{4}\)\s*$', '', title).strip()
    t = re.sub(r'\s*\b\d{4}\b\s*$', '', t).strip()
    return t

def remove_colon_subtitle(title):
    return title.split(':')[0].strip()

def first_two_words(title):
    words = title.split()
    return ' '.join(words[:2]) if len(words) > 2 else title


# ── TMDB search ────────────────────────────────────────────────────────────

def search_tmdb(session, endpoint, query, year=None, year_param='year'):
    params = {'query': query, 'page': 1}
    if year:
        params[year_param] = year
    try:
        r = session.get(f'{BASE_URL}/{endpoint}', params=params, timeout=10)
        r.raise_for_status()
        results = r.json().get('results', [])
        if results:
            hit      = results[0]
            poster   = POSTER_BASE + hit['poster_path'] if hit.get('poster_path') else None
            overview = hit.get('overview') or None
            tmdb_id  = hit.get('id')
            media_type = hit.get('media_type', 'movie') if endpoint == 'search/multi' else endpoint.split('/')[1]
            return poster, overview, tmdb_id, media_type
    except Exception:
        pass
    return None, None, None, None


# ── Details fetch: runtime, release_date, language, imdb_rating ───────────

def fetch_movie_details(session, tmdb_id, media_type='movie'):
    """
    Call /movie/{id} or /tv/{id} for runtime, release_date, language.
    Call /movie/{id}/external_ids for imdb_id, then /find for IMDB rating
    via the OMDB-style approach — or use TMDB's vote_average as proxy.
    """
    details = {
        'runtime':      None,
        'release_date': None,
        'language':     None,
        'imdb_rating':  None,
        'imdb_id':      None,
    }
    if not tmdb_id:
        return details

    endpoint = 'movie' if media_type == 'movie' else 'tv'

    try:
        r = session.get(f'{BASE_URL}/{endpoint}/{tmdb_id}', timeout=10)
        r.raise_for_status()
        d = r.json()

        if media_type == 'movie':
            details['runtime']      = d.get('runtime')                # minutes (int)
            details['release_date'] = d.get('release_date')           # "YYYY-MM-DD"
        else:
            # TV show: use episode_run_time list or first_air_date
            runtimes = d.get('episode_run_time', [])
            details['runtime']      = runtimes[0] if runtimes else None
            details['release_date'] = d.get('first_air_date')

        details['language']    = d.get('original_language')           # ISO 639-1 e.g. "en"
        # TMDB vote_average as a proxy for IMDB-style rating (0–10 scale)
        details['imdb_rating'] = round(float(d['vote_average']), 1) if d.get('vote_average') else None
        details['imdb_id']     = d.get('imdb_id')                     # "tt1234567" (movies only)

    except Exception:
        pass

    return details


# ── Videos fetch: YouTube trailer ─────────────────────────────────────────

def fetch_videos(session, tmdb_id, media_type='movie'):
    """
    Call /movie/{id}/videos or /tv/{id}/videos.
    Returns the YouTube key of the first Official Trailer,
    falling back to any Trailer, then any Teaser.
    """
    if not tmdb_id:
        return None

    endpoint = 'movie' if media_type == 'movie' else 'tv'

    try:
        r = session.get(f'{BASE_URL}/{endpoint}/{tmdb_id}/videos', timeout=10)
        r.raise_for_status()
        videos = r.json().get('results', [])

        youtube_videos = [v for v in videos if v.get('site') == 'YouTube']

        # Priority: Official Trailer → any Trailer → Teaser
        for priority in [
            lambda v: v.get('type') == 'Trailer' and v.get('official'),
            lambda v: v.get('type') == 'Trailer',
            lambda v: v.get('type') == 'Teaser',
        ]:
            hits = [v for v in youtube_videos if priority(v)]
            if hits:
                return hits[0]['key']   # e.g. "dQw4w9WgXcQ"

    except Exception:
        pass

    return None


# ── Credits fetch: cast + director ────────────────────────────────────────

def fetch_credits(session, tmdb_id, media_type='movie'):
    """
    Call /movie/{id}/credits or /tv/{id}/aggregate_credits.
    Returns:
        cast     : comma-separated string of top-5 actor names
        director : comma-separated director name(s) (movies) or
                   creator name(s) (TV)
    """
    if not tmdb_id:
        return None, None

    endpoint = 'movie' if media_type == 'movie' else 'tv'
    credits_path = 'credits' if media_type == 'movie' else 'aggregate_credits'

    try:
        r = session.get(f'{BASE_URL}/{endpoint}/{tmdb_id}/{credits_path}', timeout=10)
        r.raise_for_status()
        data = r.json()

        # ── Cast (top 5 billed actors) ─────────────────────────────────
        cast_list = data.get('cast', [])
        # For aggregate_credits (TV), actor name is under 'name' too
        top_cast  = [c['name'] for c in cast_list[:5] if c.get('name')]
        cast_str  = ', '.join(top_cast) if top_cast else None

        # ── Director ──────────────────────────────────────────────────
        crew_list = data.get('crew', [])
        if media_type == 'movie':
            directors = [c['name'] for c in crew_list if c.get('job') == 'Director']
        else:
            # TV: fetch created_by from the show details (already in fetch_movie_details),
            # but we can also look for 'Series Director' or 'Creator' in crew
            directors = [c['name'] for c in crew_list if c.get('department') == 'Directing'
                         and c.get('job') in ('Director', 'Series Director')][:3]

        director_str = ', '.join(directors) if directors else None

        return cast_str, director_str

    except Exception:
        pass

    return None, None


# ── Main per-movie fetch ───────────────────────────────────────────────────

def fetch_movie(movie):
    """Fetch one movie from TMDB — runs in a thread."""
    session = requests.Session()
    session.params = {'api_key': TMDB_API_KEY, 'language': 'en-US'}

    raw      = movie['title']
    mid      = movie['movie_id']
    year     = extract_year(raw)
    noyear   = remove_year_suffix(raw)
    stripped = remove_all_years(raw)
    nosub    = remove_colon_subtitle(stripped)
    short    = first_two_words(stripped)

    strategies = [
        ('search/movie', noyear,   year,  'year'),
        ('search/movie', noyear,   None,  'year'),
        ('search/movie', stripped, year,  'year'),
        ('search/movie', stripped, None,  'year'),
        ('search/movie', nosub,    year,  'year'),
        ('search/movie', nosub,    None,  'year'),
        ('search/movie', short,    None,  'year'),
        ('search/tv',    noyear,   year,  'first_air_date_year'),
        ('search/tv',    stripped, None,  'first_air_date_year'),
        ('search/tv',    nosub,    None,  'first_air_date_year'),
        ('search/multi', noyear,   None,  'year'),
        ('search/multi', stripped, None,  'year'),
        ('search/multi', nosub,    None,  'year'),
    ]

    poster = overview = tmdb_id = None
    media_type = 'movie'

    for endpoint, query, yr, yr_param in strategies:
        if not query:
            continue
        p, o, tid, mt = search_tmdb(session, endpoint, query, yr, yr_param)
        if p or o or tid:
            poster, overview, tmdb_id, media_type = p, o, tid, (mt or 'movie')
            break

    # ── Fetch extra data using tmdb_id ─────────────────────────────────
    details  = fetch_movie_details(session, tmdb_id, media_type)
    trailer  = fetch_videos(session,  tmdb_id, media_type)
    cast, director = fetch_credits(session, tmdb_id, media_type)

    return {
        'movie_id':     mid,
        'title':        raw,
        'poster_url':   poster,
        'overview':     overview,
        'trailer_key':  trailer,       # YouTube video key, e.g. "dQw4w9WgXcQ"
        'cast':         cast,          # "Actor A, Actor B, Actor C"
        'director':     director,      # "Director Name"
        'runtime':      details['runtime'],       # int (minutes)
        'release_date': details['release_date'],  # "YYYY-MM-DD"
        'language':     details['language'],      # "en"
        'imdb_rating':  details['imdb_rating'],   # float 0–10 (TMDB vote_average)
        'imdb_id':      details['imdb_id'],       # "tt1234567"
    }


# ── DB helpers ─────────────────────────────────────────────────────────────

def get_conn():
    return mysql.connector.connect(**{**DB_CONFIG, 'connection_timeout': 120})


def add_columns_if_missing(conn):
    """Add all new columns to movies table if they don't exist yet."""
    new_columns = [
        ('poster_url',   'VARCHAR(512)  DEFAULT NULL'),
        ('overview',     'TEXT          DEFAULT NULL'),
        ('trailer_key',  'VARCHAR(32)   DEFAULT NULL'),  # YouTube video key
        ('cast',         'TEXT          DEFAULT NULL'),  # comma-separated actor names
        ('director',     'VARCHAR(255)  DEFAULT NULL'),
        ('runtime',      'SMALLINT      DEFAULT NULL'),  # minutes
        ('release_date', 'DATE          DEFAULT NULL'),
        ('language',     'VARCHAR(10)   DEFAULT NULL'),  # ISO 639-1
        ('imdb_rating',  'DECIMAL(3,1)  DEFAULT NULL'),  # 0.0–10.0
        ('imdb_id',      'VARCHAR(20)   DEFAULT NULL'),  # "tt1234567"
    ]
    cursor = conn.cursor()
    for col, defn in new_columns:
        cursor.execute(f"SHOW COLUMNS FROM movies LIKE '{col}'")
        if not cursor.fetchone():
            cursor.execute(f"ALTER TABLE movies ADD COLUMN {col} {defn}")
            print(f"  ✓ Added column: {col}")
    conn.commit()
    cursor.close()


def bulk_save(conn, results):
    """Save a batch of enriched movie results to DB."""
    rows = []
    for r in results:
        # Only save rows where we got something useful
        if any(r[k] for k in ('poster_url', 'overview', 'trailer_key', 'cast',
                               'director', 'runtime', 'release_date', 'imdb_rating')):
            rows.append((
                r['poster_url'],
                r['overview'],
                r['trailer_key'],
                r['cast'],
                r['director'],
                r['runtime'],
                r['release_date'] or None,
                r['language'],
                r['imdb_rating'],
                r['imdb_id'],
                r['movie_id'],
            ))

    if not rows:
        return 0

    cursor = conn.cursor()
    cursor.executemany("""
        UPDATE movies SET
            poster_url   = COALESCE(%s, poster_url),
            overview     = COALESCE(%s, overview),
            trailer_key  = COALESCE(%s, trailer_key),
            cast         = COALESCE(%s, cast),
            director     = COALESCE(%s, director),
            runtime      = COALESCE(%s, runtime),
            release_date = COALESCE(%s, release_date),
            language     = COALESCE(%s, language),
            imdb_rating  = COALESCE(%s, imdb_rating),
            imdb_id      = COALESCE(%s, imdb_id)
        WHERE movie_id = %s
    """, rows)
    conn.commit()
    cursor.close()
    return len(rows)


def get_unfetched_movies(conn, mode='all'):
    """
    Return movies that still need data fetched, based on mode:
      'all'     — missing poster_url (initial full fetch)
      'details' — missing runtime or release_date
      'media'   — missing trailer_key or cast
    """
    cursor = conn.cursor(dictionary=True)

    if mode == 'details':
        cursor.execute(
            "SELECT movie_id, title FROM movies "
            "WHERE runtime IS NULL OR release_date IS NULL "
            "ORDER BY movie_id"
        )
    elif mode == 'media':
        cursor.execute(
            "SELECT movie_id, title FROM movies "
            "WHERE trailer_key IS NULL OR cast IS NULL "
            "ORDER BY movie_id"
        )
    else:  # 'all'
        cursor.execute(
            "SELECT movie_id, title FROM movies "
            "WHERE poster_url IS NULL "
            "ORDER BY movie_id"
        )

    movies = cursor.fetchall()
    cursor.close()
    return movies


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Fetch TMDB data for movies.')
    parser.add_argument('--details', action='store_true', help='Re-fetch runtime/release/language/rating')
    parser.add_argument('--media',   action='store_true', help='Re-fetch trailer + cast/director')
    args = parser.parse_args()

    if args.details:
        mode = 'details'
    elif args.media:
        mode = 'media'
    else:
        mode = 'all'

    print(f"Connecting to '{DB_CONFIG['database']}' at '{DB_CONFIG['host']}'...")
    conn = get_conn()
    print("Connected.\n")

    add_columns_if_missing(conn)

    movies = get_unfetched_movies(conn, mode)
    total  = len(movies)

    if total == 0:
        print(f"Nothing to fetch for mode='{mode}'. All movies already have this data.")
        conn.close()
        return

    print(f"Mode     : {mode}")
    print(f"Movies   : {total} to process")
    print(f"Workers  : {MAX_WORKERS} parallel | Batch save every {BATCH_SIZE}\n")

    updated   = 0
    notfound  = 0
    completed = 0
    start     = time.time()

    for batch_start in range(0, total, BATCH_SIZE):
        batch = movies[batch_start:batch_start + BATCH_SIZE]

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            results = list(executor.map(fetch_movie, batch))

        with db_lock:
            try:
                saved = bulk_save(conn, results)
            except mysql.connector.errors.OperationalError:
                conn  = get_conn()
                saved = bulk_save(conn, results)

        updated   += saved
        notfound  += len(batch) - saved
        completed += len(batch)

        elapsed   = time.time() - start
        rate      = completed / elapsed if elapsed > 0 else 1
        remaining = (total - completed) / rate if rate > 0 else 0

        print(
            f"[{completed}/{total}] "
            f"✓ {updated} saved  ✗ {notfound} not found  "
            f"| {elapsed/60:.1f}m elapsed  ~{remaining/60:.1f}m left"
        )

    conn.close()
    elapsed = time.time() - start
    print(f"\n── Done ──────────────────────────────────────────")
    print(f"  Updated  : {updated}/{total}")
    print(f"  Not found: {notfound}")
    print(f"  Time     : {elapsed/60:.1f} minutes")


if __name__ == '__main__':
    main()