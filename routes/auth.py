from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from models.db import get_connection

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email    = request.form['email']
        password = request.form['password']
        password_hash = generate_password_hash(password)
        try:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (%s,%s,%s)",
                (username, email, password_hash)
            )
            conn.commit()
            cursor.close()
            conn.close()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('auth.login'))
        except Exception:
            flash('Username or email already exists.', 'danger')
    return render_template('register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn   = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        # Block ML placeholder accounts from logging in
        if user and user['password_hash'] == 'ml_placeholder':
            flash('Invalid username or password.', 'danger')
            return render_template('login.html')

        if user and check_password_hash(user['password_hash'], password):
            if user.get('is_banned'):
                flash('Your account has been suspended. Contact support.', 'danger')
                return render_template('login.html')
            session['user_id']  = user['user_id']
            session['username'] = user['username']
            session['is_admin'] = bool(user.get('is_admin', 0))
            flash(f"Welcome back, {username}!", 'success')
            return redirect(url_for('items.browse'))
        flash('Invalid username or password.', 'danger')
    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    from models.db import get_user_ratings, get_watchlist
    ratings   = get_user_ratings(session['user_id'])
    watchlist = get_watchlist(session['user_id'])
    return render_template('profile.html',
                           ratings=ratings,
                           watchlist=watchlist)