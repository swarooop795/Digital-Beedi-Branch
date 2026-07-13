from flask import Flask
import os
from app.models.database import init_db, close_connection, get_db
from app.models.user import User

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')
app.config['RAZORPAY_KEY_ID'] = os.getenv('RAZORPAY_KEY_ID')
app.config['RAZORPAY_KEY_SECRET'] = os.getenv('RAZORPAY_KEY_SECRET')
app.config['RAZORPAY_ACCOUNT_NUMBER'] = os.getenv('RAZORPAY_ACCOUNT_NUMBER', '2323230032510196')
# Low-stock threshold used in templates (can be overridden via environment variable)
try:
    app.config['LOW_STOCK_THRESHOLD'] = int(os.getenv('LOW_STOCK_THRESHOLD', '10'))
except Exception:
    app.config['LOW_STOCK_THRESHOLD'] = 10

# Setup basic file logging for uncaught exceptions so 500s are easier to diagnose locally
import logging
from logging.handlers import RotatingFileHandler
import uuid
import traceback

log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
log_dir = os.path.abspath(log_dir)
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'errors.log')
handler = RotatingFileHandler(log_file, maxBytes=2 * 1024 * 1024, backupCount=3)
handler.setLevel(logging.INFO)
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
app.logger.addHandler(handler)

from flask import request, render_template, session, make_response
from werkzeug.exceptions import HTTPException


@app.errorhandler(Exception)
def handle_uncaught_exception(e):
    """Global error handler that logs exception and shows a friendly page with reference id.

    Treat HTTP exceptions (404, 405, etc.) specially: don't convert them to 500s and return
    the original HTTP response. For other exceptions, log the traceback and return a
    friendly error page with a short reference id.
    """
    err_id = uuid.uuid4().hex[:8]

    # determine current user (best-effort)
    try:
        user = None
        if 'user_id' in session:
            user = session.get('user_id')
    except Exception:
        user = None

    if isinstance(e, HTTPException):
        # HTTP exceptions are not server errors - log at INFO and return original response
        app.logger.info('HTTP error id=%s path=%s method=%s user=%s code=%s',
                        err_id, request.path, request.method, user, getattr(e, 'code', None))
        # return the Werkzeug response for this HTTPException
        return e.get_response()

    # Non-HTTP exceptions: log full traceback for debugging and show friendly page
    tb = traceback.format_exc()
    app.logger.error('Error id=%s path=%s method=%s user=%s\n%s', err_id, request.path, request.method, user, tb)
    return render_template('error.html', error_id=err_id), 500


# serve a simple empty favicon to avoid repeated 404/500 noise from browsers requesting /favicon.ico
@app.route('/favicon.ico')
def favicon():
    # Returning 204 No Content is fine for dev servers when no favicon is provided.
    return ('', 204)

# Initialize SQLite DB
with app.app_context():
    init_db()
    User.create_admin_if_not_exists()

# Register teardown
from flask import g
app.teardown_appcontext(close_connection)


from app.routes import main_routes, worker_routes, inventory_routes, analytics_routes, auth_routes, payment_dashboard_routes, payment_routes, batch_payment_routes
from app.payment_report import bp as payment_report_bp

# Register blueprints
app.register_blueprint(main_routes.bp)
app.register_blueprint(worker_routes.bp)
app.register_blueprint(inventory_routes.bp)
app.register_blueprint(analytics_routes.bp)
app.register_blueprint(auth_routes.bp)
app.register_blueprint(payment_report_bp)


@app.context_processor
def inject_unread_notifications():
    """Inject unread_notifications_count into all templates for the current user."""
    try:
        from flask import session
        if 'user_id' in session:
            db = get_db()
            row = db.execute('SELECT COUNT(*) AS c FROM notifications WHERE user_id = ? AND is_read = 0', (session['user_id'],)).fetchone()
            count = int(row['c']) if row else 0
            # also fetch recent notifications (limit 5) to show in navbar dropdown
            try:
                recent = db.execute('SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 5', (session['user_id'],)).fetchall()
                recent_list = [dict(r) for r in recent]
            except Exception:
                recent_list = []
        else:
            count = 0
            recent_list = []
    except Exception:
        count = 0
        recent_list = []
    # expose low stock threshold to templates so we don't hard-code the number in many places
    return {'unread_notifications_count': count, 'recent_notifications': recent_list,
        'low_stock_threshold': app.config.get('LOW_STOCK_THRESHOLD', 10)}