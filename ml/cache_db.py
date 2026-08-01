"""
DB-backed cache for ML models.
Stores serialized pickle blobs in MySQL so they survive Railway redeploys.
"""
import pickle
import hashlib
import mysql.connector
from config import DB_CONFIG


def get_connection():
    return mysql.connector.connect(**DB_CONFIG)


def ensure_cache_table():
    """Create ml_cache table if it doesn't exist."""
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ml_cache (
            cache_key    VARCHAR(64)  PRIMARY KEY,
            data_hash    VARCHAR(32)  NOT NULL,
            model_blob   LONGBLOB     NOT NULL,
            built_at     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()


def load_from_db(cache_key):
    """Load a cached model blob from DB. Returns None if not found."""
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT model_blob FROM ml_cache WHERE cache_key = %s",
            (cache_key,)
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row:
            return pickle.loads(row[0])
    except Exception as e:
        print(f"[Cache] Load error: {e}")
    return None


def save_to_db(cache_key, data_hash, obj, built_by=None):
    try:
        blob   = pickle.dumps(obj, protocol=4)
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ml_cache (cache_key, data_hash, model_blob, built_by)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                data_hash  = VALUES(data_hash),
                model_blob = VALUES(model_blob),
                built_by   = VALUES(built_by),
                built_at   = CURRENT_TIMESTAMP
        """, (cache_key, data_hash, blob, built_by))
        conn.commit()
        cursor.close()
        conn.close()
        print(f"[Cache] Saved '{cache_key}' to DB ({len(blob)//1024}KB)")
        return True
    except Exception as e:
        print(f"[Cache] Save error: {e}")
        return False


def get_cached_hash(cache_key):
    """Get the data_hash stored for a cache key."""
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT data_hash FROM ml_cache WHERE cache_key = %s",
            (cache_key,)
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        print(f"[Cache] Hash check error: {e}")
        return None