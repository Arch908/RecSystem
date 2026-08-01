"""
Run this ONCE to create all tables in your database.
Usage: python init_db.py
"""
import mysql.connector
from config import DB_CONFIG

SQL_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS users (
        user_id       INT AUTO_INCREMENT PRIMARY KEY,
        username      VARCHAR(80)  UNIQUE NOT NULL,
        email         VARCHAR(120) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        is_admin      TINYINT(1)   NOT NULL DEFAULT 0,
        is_banned     TINYINT(1)   NOT NULL DEFAULT 0,
        created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS movies (
        movie_id   INT PRIMARY KEY,
        title      VARCHAR(255) NOT NULL,
        genres     VARCHAR(255),
        poster_url VARCHAR(512) DEFAULT NULL,
        overview   TEXT         DEFAULT NULL,
        trailer_key  VARCHAR(32)  DEFAULT NULL,
        cast         TEXT         DEFAULT NULL,
        director     VARCHAR(500) DEFAULT NULL,
        runtime      SMALLINT     DEFAULT NULL,
        release_date DATE         DEFAULT NULL,
        language     VARCHAR(10)  DEFAULT NULL,
        imdb_rating  DECIMAL(3,1) DEFAULT NULL,
        imdb_id      VARCHAR(20)  DEFAULT NULL
    )""",

    """CREATE TABLE IF NOT EXISTS user_preferences (
        user_id          INT PRIMARY KEY,
        favorite_genres  VARCHAR(500) NOT NULL DEFAULT '',
        completed_at     TIMESTAMP NULL DEFAULT NULL,
        updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
    )""",

    """CREATE TABLE IF NOT EXISTS ratings (
        id        INT AUTO_INCREMENT PRIMARY KEY,
        user_id   INT   NOT NULL,
        movie_id  INT   NOT NULL,
        rating    FLOAT NOT NULL,
        timestamp BIGINT,
        FOREIGN KEY (user_id)  REFERENCES users(user_id),
        FOREIGN KEY (movie_id) REFERENCES movies(movie_id),
        UNIQUE KEY unique_rating (user_id, movie_id)
    )""",

    """CREATE TABLE IF NOT EXISTS watchlist (
        id       INT AUTO_INCREMENT PRIMARY KEY,
        user_id  INT NOT NULL,
        movie_id INT NOT NULL,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id)  REFERENCES users(user_id),
        FOREIGN KEY (movie_id) REFERENCES movies(movie_id),
        UNIQUE KEY unique_watchlist (user_id, movie_id)
    )""",

    """CREATE TABLE IF NOT EXISTS not_interested (
        id         INT AUTO_INCREMENT PRIMARY KEY,
        user_id    INT NOT NULL,
        movie_id   INT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
        FOREIGN KEY (movie_id) REFERENCES movies(movie_id) ON DELETE CASCADE,
        UNIQUE KEY unique_not_interested (user_id, movie_id)
    )""",

    """CREATE TABLE IF NOT EXISTS recommendation_logs (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT   NOT NULL,
    movie_id   INT   NOT NULL,
    score      FLOAT,
    method     VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id)  REFERENCES users(user_id),
    FOREIGN KEY (movie_id) REFERENCES movies(movie_id)
)""",
]


def add_cache_table(conn):
    """Add ml_cache table for storing SVD and content models."""
    print("Adding ml_cache table...")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ml_cache (
            cache_key  VARCHAR(64) PRIMARY KEY,
            data_hash  VARCHAR(32) NOT NULL,
            model_blob LONGBLOB    NOT NULL,
             built_by   INT         DEFAULT NULL,
            built_at   TIMESTAMP   DEFAULT CURRENT_TIMESTAMP
                                   ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (built_by) REFERENCES users(user_id)
                                   ON DELETE SET NULL
        )
    """)
    conn.commit()
    cursor.close()
    print("  ✓ Table ml_cache ready")


def main():
    print(f"Connecting to '{DB_CONFIG['database']}' at '{DB_CONFIG['host']}'...")
    conn   = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    for sql in SQL_STATEMENTS:
        table_name = sql.strip().split('EXISTS')[1].split('(')[0].strip()
        cursor.execute(sql)
        print(f"  ✓ Table {table_name} ready")

    conn.commit()
    cursor.close()

    add_cache_table(conn)

    conn.close()
    print("\nAll tables created successfully.")
    print("\nTo make a user an admin, run this in MySQL:")
    print("  UPDATE users SET is_admin = 1 WHERE username = 'your_username';")


if __name__ == '__main__':
    main()