from flask import render_template, session, redirect, url_for
from app.models.database import get_db
from datetime import datetime

# reuse main blueprint and admin helper
from app.routes.main_routes import bp as main_bp, admin_required

bp = main_bp


@bp.route('/payment-dashboard')
@admin_required
def payment_dashboard():
    db = get_db()
    today = datetime.now().date()
    month_start = today.replace(day=1)
    
    # Get statistics
    stats = {}
    
    # Today's payments
    today_data = db.execute('''
        SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total
        FROM payments
        WHERE DATE(payment_date) = DATE(?)
    ''', (today.isoformat(),)).fetchone()
    stats['today_count'] = today_data['count']
    stats['today_total'] = today_data['total']
    
    # This month's payments
    month_data = db.execute('''
        SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total
        FROM payments
        WHERE DATE(payment_date) >= DATE(?)
        AND DATE(payment_date) <= DATE(?)
    ''', (month_start.isoformat(), today.isoformat())).fetchone()
    stats['month_count'] = month_data['count']
    stats['month_total'] = month_data['total']
    
    # Pending confirmations
    pending_data = db.execute('''
        SELECT COUNT(*) as count
        FROM payments
        WHERE status = 'pending_confirmation'
    ''').fetchone()
    stats['pending_count'] = pending_data['count']
    
    # Get payment method distribution
    method_data = db.execute('''
        SELECT payment_method, COUNT(*) as count
        FROM payments
        WHERE DATE(payment_date) >= DATE(?)
        GROUP BY payment_method
    ''', (month_start.isoformat(),)).fetchall()
    
    payment_methods = []
    method_counts = []
    for row in method_data:
        payment_methods.append(row['payment_method'])
        method_counts.append(row['count'])
    
    # Get daily payment trend for last 7 days
    trend_data = db.execute('''
        SELECT DATE(payment_date) as date,
               COALESCE(SUM(amount), 0) as total
        FROM payments
        WHERE DATE(payment_date) >= DATE(?, '-6 days')
        GROUP BY DATE(payment_date)
        ORDER BY date
    ''', (today.isoformat(),)).fetchall()
    
    trend_dates = []
    trend_amounts = []
    for row in trend_data:
        trend_dates.append(row['date'])
        trend_amounts.append(float(row['total']))
    
    # Get pending payments
    pending_payments = db.execute('''
        SELECT p.*, w.name as worker_name
        FROM payments p
        JOIN workers w ON p.worker_id = w.id
        WHERE p.status = 'pending_confirmation'
        ORDER BY p.payment_date DESC
    ''').fetchall()
    
    # Get recent payments
    recent_payments = db.execute('''
        SELECT p.*, w.name as worker_name
        FROM payments p
        JOIN workers w ON p.worker_id = w.id
        ORDER BY p.payment_date DESC
        LIMIT 50
    ''').fetchall()
    
    return render_template('payment_dashboard.html',
                         stats=stats,
                         payment_methods=payment_methods,
                         method_counts=method_counts,
                         trend_dates=trend_dates,
                         trend_amounts=trend_amounts,
                         pending_payments=pending_payments,
                         recent_payments=recent_payments)