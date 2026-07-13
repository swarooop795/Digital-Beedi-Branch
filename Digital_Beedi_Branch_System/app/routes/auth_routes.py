from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from app.models.user import User
from app.models.database import get_db
from app.utils.security import (
    check_password_strength, get_failed_attempts, record_failed_attempt,
    reset_failed_attempts, is_account_locked, session_timeout_required, rate_limit,
    init_session_security, is_session_valid
)
from datetime import datetime, timedelta
import random
from werkzeug.security import check_password_hash, generate_password_hash
from flask import jsonify

bp = Blueprint('auth', __name__)

@bp.before_request
def check_session():
    if 'user_id' in session and not is_session_valid():
        session.clear()
        flash('Your session has expired. Please login again.', 'warning')
        return redirect(url_for('auth.login'))

@bp.route('/admin-login', methods=['GET', 'POST'])
@rate_limit()
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Do not enforce password strength on login (only on creation).
        # Previously this check blocked valid existing accounts using older passwords.
            
        user = User.get_by_username(username)
        
        if is_account_locked(username):
            flash('Account is temporarily locked. Please try again later.', 'error')
            return render_template('admin_login.html')
            
        if user and user['role'] == 'admin' and User.check_password(user, password):
            reset_failed_attempts(username)

            # Admins: skip 2FA. Initialize secure admin session directly using
            # the same session helper used elsewhere.
            init_session_security(user['id'], 'admin', user['username'])
            flash('Logged in successfully!', 'success')
            return redirect(url_for('main.admin_dashboard'))
            
        record_failed_attempt(username)
        attempts_left = 3 - get_failed_attempts(username)
        
        if attempts_left > 0:
            flash(f'Invalid credentials. {attempts_left} attempts remaining.', 'error')
        else:
            flash('Account temporarily locked due to multiple failed attempts.', 'error')
            
    return render_template('admin_login.html')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    """Compatibility alias: some templates call `auth.login` — forward to admin_login."""
    return admin_login()

@bp.route('/worker-login', methods=['GET', 'POST'])
@rate_limit()
def worker_login():
    db = get_db()
    if request.method == 'POST':
        # Password-only worker login (no OTP)
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash('Please enter both username and password', 'error')
            return render_template('worker_login.html')

        user = User.get_by_username(username)
        # If no user found by username, allow login using numeric worker ID:
        # admin can give workers their ID as username; map worker ID -> user_id
        if not user and username.isdigit():
            try:
                worker_row = db.execute('SELECT user_id FROM workers WHERE id = ?', (int(username),)).fetchone()
                if worker_row and worker_row['user_id']:
                    user = db.execute('SELECT * FROM users WHERE id = ?', (worker_row['user_id'],)).fetchone()
            except Exception:
                user = None

        if not user:
            flash('Account not found. Please contact your Branch Manager.', 'error')
            return render_template('worker_login.html')

        if is_account_locked(username):
            flash('Account temporarily locked. Please try again later.', 'error')
            return render_template('worker_login.html')

        if User.check_password(user, password):
            reset_failed_attempts(username)
            # find linked worker profile
            worker = db.execute('SELECT * FROM workers WHERE user_id = ?', (user['id'],)).fetchone()
            if not worker:
                flash('No worker profile linked to this account. Please contact your Branch Manager.', 'error')
                return render_template('worker_login.html')

            init_session_security(user['id'], 'worker', user['username'])
            session['worker_id'] = worker['id']
            flash('Logged in successfully!', 'success')
            return redirect(url_for('worker_routes.worker_dashboard'))
        else:
            record_failed_attempt(username)
            attempts_left = 3 - get_failed_attempts(username)
            if attempts_left > 0:
                flash(f'Invalid credentials. {attempts_left} attempts remaining.', 'error')
            else:
                flash('Account temporarily locked due to multiple failed attempts.', 'error')
            return render_template('worker_login.html')

    return render_template('worker_login.html')

@bp.route('/2fa', methods=['GET', 'POST'])
def two_factor_auth():
    # 2FA has been removed from the project. Leave this endpoint as a harmless redirect.
    return redirect(url_for('auth.admin_login'))

@bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.index'))
    if 'user_id' not in session or session.get('role') != 'admin':
        flash('Only admin can register customers.', 'danger')
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        try:
            User.create_user(username, password, 'customer', customer_of=session['user_id'])
            flash('Customer registered successfully!', 'success')
            return redirect(url_for('main.admin_dashboard'))
        except Exception as e:
            flash('Registration failed: ' + str(e), 'danger')
    return render_template('register.html')

@bp.route('/register-admin', methods=['GET', 'POST'])
def register_admin():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        try:
            User.create_user(username, password, 'admin')
            flash('Admin registered successfully!', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            flash('Registration failed: ' + str(e), 'danger')
    return render_template('register.html')


@bp.route('/set-worker-password', methods=['POST'])
def set_worker_password():
    # Admin-only
    if session.get('role') != 'admin':
        return jsonify(success=False, error='Not authorized'), 403
    worker_id = request.form.get('worker_id')
    username = request.form.get('username')
    password = request.form.get('password')
    if not (worker_id and username and password):
        return jsonify(success=False, error='Missing fields')
    db = get_db()
    try:
        # Check existing user
        existing = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if existing:
            # Update password
            hashed = generate_password_hash(password)
            db.execute('UPDATE users SET password = ? WHERE id = ?', (hashed, existing['id']))
            user_id = existing['id']
        else:
            # Create user with role worker (fallback to customer if DB restricts)
            from app.models.user import User
            try:
                User.create_user(username, password, 'worker')
            except Exception:
                User.create_user(username, password, 'customer')
            user = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
            user_id = user['id'] if user else None

        if user_id:
            db.execute('UPDATE workers SET user_id = ? WHERE id = ?', (user_id, worker_id))
        db.commit()
        return jsonify(success=True)
    except Exception as e:
        db.rollback()
        return jsonify(success=False, error=str(e))