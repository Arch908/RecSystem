# Movie Recommendation System (RecSys)

A full-stack movie discovery application using collaborative filtering (truncated SVD), content-based filtering (TF-IDF on title and genres), and weighted hybrid ranking.

## Main features
- Session-based registration and login
- Movie browse, search, genres, details, ratings, watchlist, and trending lists
- Collaborative, content-based, and hybrid recommendations
- Plain-language recommendation explanations
- Admin dashboard and model-cache management

## Setup
1. Create a MySQL database named `recsys`.
2. Copy `.env.example` values into your environment and set a private `SECRET_KEY` and `TMDB_API_KEY`.
3. Install Python packages: `pip install -r requirements.txt`.
4. Initialize tables: `python init_db.py`.
5. Import MovieLens data: `python data/preprocess.py`.
6. Build the frontend: `cd frontend && npm install && npm run build`.
7. Run the backend: `python app.py`.

## Security notes
Production deployments must not use the development secret or default database password. Session cookies are HTTP-only and use SameSite=Lax; Secure cookies are enabled when `FLASK_ENV=production`.

## Offline recommendation evaluation

The project includes a leakage-free offline evaluation for **Precision@10** and **Recall@10**. It uses a reproducible per-user holdout split: 20% of each eligible user's ratings of 4.0 or higher are hidden as relevant test items, and the recommendation models are built only from the remaining ratings.

```bash
python evaluate_recommendations.py
```

The command writes `evaluation_results.json`. The latest results can also be retrieved by an authenticated administrator through `GET /api/admin/offline-evaluation`.


## Improvements included
- Leakage-free Precision@10, Recall@10 and F1@10 evaluation.
- Automatic grid search for the best CF/CBF hybrid weight.
- Admin dashboard display of offline evaluation metrics.
- Cold-start starter recommendations for users with fewer than 10 ratings.
- Human-readable recommendation explanations.
- Stronger validation and process-local model-cache invalidation after ratings change.

Re-run tuning with `python evaluate_recommendations.py`; the application automatically loads the selected weights from `evaluation_results.json`.
