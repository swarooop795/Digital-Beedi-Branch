from datetime import datetime, timedelta
from functools import wraps
from flask import session, redirect, url_for, flash, request
import re
from werkzeug.security import generate_password_hash, check_password_hash

# Prefer a real Redis server, but fall back to fakeredis for local dev if not available.
try:
    import redis
    try:
        redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        # test connectivity
        redis_client.ping()
    except Exception:
        # real redis not reachable — fall back to fakeredis
        try:
            import fakeredis
            redis_client = fakeredis.FakeStrictRedis(decode_responses=True)
            # No-op: local fake redis in memory
        except Exception:
            redis_client = None
except Exception:
    # redis package not installed; try fakeredis
    try:
        import fakeredis
        redis_client = fakeredis.FakeStrictRedis(decode_responses=True)
    except Exception:
        redis_client = None

# If neither redis nor fakeredis are available, provide a tiny in-memory fallback
if redis_client is None:
    class _LocalRedis:
        def __init__(self):
            self._store = {}

        def get(self, key):
            return self._store.get(key)

        def incr(self, key):
            val = int(self._store.get(key, '0')) + 1
            self._store[key] = str(val)
            return val

        def setex(self, key, time, value):
            # store as string; expiry not implemented in fallback
            self._store[key] = str(value)

        def expire(self, key, time):
            # no-op for fallback
            return True

        def delete(self, key):
            return self._store.pop(key, None)

    redis_client = _LocalRedis()

def check_password_strength(password):
    """Check password strength and return (is_valid, message)"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    checks = [
        (r"[A-Z]", "uppercase letter"),
        (r"[a-z]", "lowercase letter"),
        (r"[0-9]", "number"),
        (r"[!@#$%^&*(),.?\":{}|<>]", "special character")
    ]
    
    missing = [desc for pattern, desc in checks if not re.search(pattern, password)]
    
    if missing:
        return False, f"Password must contain at least one {', '.join(missing)}"
    
    return True, "Password is strong"

def get_failed_attempts(username):
    """Get number of failed login attempts"""
    key = f"login_attempts:{username}"
    attempts = redis_client.get(key)
    return int(attempts) if attempts else 0

def record_failed_attempt(username):
    """Record a failed login attempt"""
    key = f"login_attempts:{username}"
    redis_client.incr(key)
    redis_client.expire(key, 1800)  # Reset after 30 minutes

def reset_failed_attempts(username):
    """Reset failed login attempts"""
    key = f"login_attempts:{username}"
    redis_client.delete(key)

def is_account_locked(username):
    """Check if account is temporarily locked"""
    attempts = get_failed_attempts(username)
    return attempts >= 5



def session_timeout_required(f):
    """Decorator to check session timeout"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'last_activity' in session:
            last_activity = datetime.fromisoformat(session['last_activity'])
            if datetime.now() - last_activity > timedelta(minutes=30):
                session.clear()
                flash('Your session has expired. Please login again.', 'warning')
                return redirect(url_for('auth.login'))
        
        session['last_activity'] = datetime.now().isoformat()
        return f(*args, **kwargs)
    return decorated_function

def rate_limit(limit=5, period=60):
    """Rate limiting decorator"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            key = f"rate_limit:{request.remote_addr}:{f.__name__}"
            count = redis_client.get(key)
            
            if count is None:
                redis_client.setex(key, period, 1)
            elif int(count) >= limit:
                flash('Too many requests. Please try again later.', 'error')
                return redirect(url_for('main.index'))
            else:
                redis_client.incr(key)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def init_session_security(user_id, role, username):
    """Initialize secure session"""
    session.clear()
    session['user_id'] = user_id
    session['role'] = role
    session['username'] = username
    session['last_activity'] = datetime.now().isoformat()
    session['created_at'] = datetime.now().isoformat()
    session['ip_address'] = request.remote_addr
    session['user_agent'] = request.user_agent.string
    # Helpful boolean flags used across the codebase
    session['is_authenticated'] = True
    session['is_admin'] = (role == 'admin')
    session['is_customer'] = (role == 'customer')

def is_session_valid():
    """Validate current session"""
    if 'created_at' not in session:
        return False
    
    created_at = datetime.fromisoformat(session['created_at'])
    if datetime.now() - created_at > timedelta(days=1):
        return False
    
    if session.get('ip_address') != request.remote_addr:
        return False
    
    if session.get('user_agent') != request.user_agent.string:
        return False
    
    return True