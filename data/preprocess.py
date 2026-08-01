import pandas as pd
import mysql.connector
import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import DB_CONFIG


def get_connection():
    config = {**DB_CONFIG, 'connection_timeout': 300}
    return mysql.connector.connect(**config)


def load_data():
    movies  = pd.read_csv(os.path.join(os.path.dirname(__file__), 'movies.csv'))
    ratings = pd.read_csv(os.path.join(os.path.dirname(__file__), 'ratings.csv'))

    # ── Load movies in batches ─────────────────────────────────────────────
    print(f"Loading {len(movies)} movies in batches...")
    conn   = get_connection()
    cursor = conn.cursor()

    BATCH  = 200
    total  = len(movies)
    loaded = 0

    for i in range(0, total, BATCH):
        batch  = movies.iloc[i:i + BATCH]
        values = [
            (int(row['movieId']), row['title'], row['genres'])
            for _, row in batch.iterrows()
        ]
        try:
            cursor.executemany(
                "INSERT IGNORE INTO movies (movie_id, title, genres) VALUES (%s, %s, %s)",
                values
            )
            conn.commit()
        except mysql.connector.errors.OperationalError:
            print(f"  Connection lost at movie {loaded}, reconnecting...")
            time.sleep(3)
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.executemany(
                "INSERT IGNORE INTO movies (movie_id, title, genres) VALUES (%s, %s, %s)",
                values
            )
            conn.commit()

        loaded += len(batch)
        print(f"  Movies: {loaded}/{total}")

    cursor.close()
    conn.close()
    print(f"✓ Movies loaded.\n")

    # ── Load ratings in batches ────────────────────────────────────────────
    sample = ratings.sample(n=min(200000, len(ratings)), random_state=42)
    print(f"Loading {len(sample)} ratings in batches...")

    conn   = get_connection()
    cursor = conn.cursor()

    # Insert placeholder ML users first
    ml_users = sample['userId'].unique()
    print(f"  Inserting {len(ml_users)} ML users...")

    user_values = [
        (int(uid) + 10000,
         f"ml_user_{int(uid) + 10000}",
         f"ml_user_{int(uid) + 10000}@example.com",
         "ml_placeholder")
        for uid in ml_users
    ]

    for i in range(0, len(user_values), BATCH):
        try:
            cursor.executemany(
                "INSERT IGNORE INTO users (user_id, username, email, password_hash) VALUES (%s, %s, %s, %s)",
                user_values[i:i + BATCH]
            )
            conn.commit()
        except mysql.connector.errors.OperationalError:
            print(f"  Connection lost at user batch {i}, reconnecting...")
            time.sleep(3)
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.executemany(
                "INSERT IGNORE INTO users (user_id, username, email, password_hash) VALUES (%s, %s, %s, %s)",
                user_values[i:i + BATCH]
            )
            conn.commit()

    print(f"  ✓ ML users inserted.")

    # Insert ratings in batches
    total  = len(sample)
    loaded = 0

    rating_values = [
        (int(row['userId']) + 10000,
         int(row['movieId']),
         float(row['rating']),
         int(row['timestamp']))
        for _, row in sample.iterrows()
    ]

    for i in range(0, total, BATCH):
        batch = rating_values[i:i + BATCH]
        try:
            cursor.executemany(
                "INSERT IGNORE INTO ratings (user_id, movie_id, rating, timestamp) VALUES (%s, %s, %s, %s)",
                batch
            )
            conn.commit()
        except mysql.connector.errors.OperationalError:
            print(f"  Connection lost at rating {loaded}, reconnecting...")
            time.sleep(3)
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.executemany(
                "INSERT IGNORE INTO ratings (user_id, movie_id, rating, timestamp) VALUES (%s, %s, %s, %s)",
                batch
            )
            conn.commit()

        loaded += len(batch)
        print(f"  Ratings: {loaded}/{total}")

    cursor.close()
    conn.close()
    print(f"\n✓ Done. {total} ratings loaded.")


if __name__ == '__main__':
    load_data()