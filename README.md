RecoSys is a full-stack movie recommendation web app built as a three-member capstone project. It combines collaborative filtering (SVD matrix factorization) with content-based filtering (TF-IDF cosine similarity) in a hybrid fusion layer to produce personalized recommendations. Movie metadata, trailers and cast come from the TMDB API, and the ratings data comes from MovieLens.

Key features

Hybrid recommender: SVD-based collaborative filtering plus TF-IDF content-based filtering
SVD fold-in projection, so new users get recommendations without a full model rebuild
Two-stage candidate filtering (percentile cap plus absolute score floor) for both CF and CB
Human-readable scores (predicted ratings and similarity percentages)
Per-user recommendation caching
TMDB integration for trailers, cast, trending and discover
Offline evaluation with Precision@K, Recall@K, F1@K, NDCG@K, Diversity and Coverage

Tech stack

Backend: Flask, Gunicorn, MySQL (Aiven)
Frontend: React, Vite
ML: scikit-learn, SciPy
Data: MovieLens, TMDB API
Deployment: Render, Aiven
