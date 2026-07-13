from app.models.database import get_db
from datetime import datetime, timedelta
from flask import url_for
from app.utils.notifications import send_worker_notification

def check_pending_payments():
    """Check for pending payments and generate reminders"""
    db = get_db()
    
    # Get all unpaid entries that are older than 2 days
    two_days_ago = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
    
    unpaid_entries = db.execute('''
        SELECT 
            b.id,
            b.worker_id,
            b.entry_time,
            b.price * b.quantity as amount,
            w.name as worker_name,
            u.id as admin_id
        FROM beedi_entries b
        JOIN workers w ON b.worker_id = w.id
        JOIN users u ON b.admin_id = u.id
        WHERE b.is_paid = 0 AND date(b.entry_time) <= ?
    ''', (two_days_ago,)).fetchall()
    
    for entry in unpaid_entries:
        # Create reminder notification (actionable)
        reminder_body = (f"Payment Reminder: ₹{entry['amount']} pending for {entry['worker_name']} "
                         f"from {entry['entry_time']}.")
        send_worker_notification(entry['admin_id'], 'Payment Reminder', reminder_body, url_for('main.wages'))
    
    db.commit()