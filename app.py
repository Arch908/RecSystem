import os
from flask import Flask, send_from_directory
from config import SECRET_KEY
from routes.auth import auth_bp
from routes.api import api_bp
from routes.admin_api import admin_api_bp

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('FLASK_ENV') == 'production',
)

app.register_blueprint(api_bp)
app.register_blueprint(admin_api_bp)

# ── Pre-warm ML models at startup (production only) ────────────────────────
# Builds the SVD + TF-IDF models once, here, instead of on a user's first
# /api/recommendations request — avoids a slow/timed-out first request.
if os.environ.get('FLASK_ENV') == 'production':
    with app.app_context():
        from ml.collaborative import get_or_build_model as cf_build
        from ml.content_based import get_or_build_model as cb_build
        print("[Startup] Pre-warming ML models...")
        cf_build()
        cb_build()
        print("[Startup] ML models ready.")


# ── Serve React SPA for all non-API routes ────────────────────────────────
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_react(path):
    dist = os.path.join(app.static_folder, 'dist')
    file_path = os.path.join(dist, path)
    if path and os.path.exists(file_path):
        return send_from_directory(dist, path)
    return send_from_directory(dist, 'index.html')


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)