from flask import Blueprint, render_template, session, redirect, url_for, request, flash, jsonify, make_response, current_app
from app.models.database import get_db
from datetime import datetime, timedelta
from functools import wraps
import json
from app.utils.notifications import send_worker_notification
import razorpay

bp = Blueprint('main', __name__)

def generate_receipt_number():
    """Generate a unique receipt number"""
    now = datetime.now()
    prefix = f"BEEDI{now.year}{now.month:02d}"
    
    db = get_db()
    last_receipt = db.execute(
        "SELECT receipt_number FROM payments WHERE receipt_number LIKE ? ORDER BY id DESC LIMIT 1",
        (f"{prefix}%",)
    ).fetchone()
    
    if last_receipt:
        last_num = int(last_receipt['receipt_number'][len(prefix):])
        new_num = last_num + 1
    else:
        new_num = 1
    
    return f"{prefix}{new_num:04d}"

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # accept either explicit boolean flag or role value
        if not (session.get('is_admin') or session.get('role') == 'admin'):
            flash('Admin access required.', 'error')
            return redirect(url_for('auth.admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@bp.route('/')
def index():
    if 'user_id' in session:
        if session.get('role') == 'admin':
            return redirect(url_for('main.admin_dashboard'))
        elif session.get('role') == 'customer':
            return redirect(url_for('main.customer_dashboard'))
    return render_template('index.html')

@bp.route('/admin-dashboard')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))
    return render_template('admin_dashboard.html')

@bp.route('/customer-dashboard')
def customer_dashboard():
    if session.get('role') != 'customer':
        return redirect(url_for('auth.admin_login'))
    return render_template('customer_dashboard.html')

@bp.route('/worker/<int:worker_id>')
def worker_details(worker_id):
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))
    
    db = get_db()
    worker = db.execute('SELECT * FROM workers WHERE id = ?', (worker_id,)).fetchone()
    if not worker:
        flash('Worker not found', 'error')
        return redirect(url_for('main.index'))
        
    # Query payments with receipt numbers
    payments = db.execute('''
        SELECT p.id, p.payment_date, p.amount, p.payment_method, p.status, p.payment_details,
               p.receipt_number, p.payment_comment
        FROM payments p
        WHERE p.worker_id = ?
        ORDER BY p.payment_date DESC
    ''', (worker_id,)).fetchall()
    
    # Allow both dict and tuple access for compatibility
    if isinstance(worker, tuple):
        worker_dict = {}
        cols = [r['name'] for r in db.execute("PRAGMA table_info(workers)").fetchall()]
        for i, col in enumerate(cols):
            worker_dict[col] = worker[i]
        worker = worker_dict
    
    return render_template('worker_details.html', worker=worker, payments=payments)

@bp.route('/beedi-entry', methods=['GET', 'POST'])
def beedi_entry():
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))
    db = get_db()
    workers = db.execute('SELECT * FROM workers WHERE admin_id = ?', (session['user_id'],)).fetchall()
    if request.method == 'POST':
        worker_id = request.form['worker_id']
        price = float(request.form['price'])
        quantity = int(request.form['quantity'])
        is_paid = int(request.form.get('is_paid', 0))
        entry_time = datetime.now().isoformat(sep=' ', timespec='seconds')
        entry_cur = db.execute('INSERT INTO beedi_entries (worker_id, price, quantity, entry_time, admin_id, is_paid) VALUES (?, ?, ?, ?, ?, ?)',
                   (worker_id, price, quantity, entry_time, session['user_id'], is_paid))
        entry_id = entry_cur.lastrowid
        # Notify the worker that a beedi entry (wage) was recorded for them
        worker_user = db.execute('SELECT user_id FROM workers WHERE id = ?', (worker_id,)).fetchone()
        if worker_user and worker_user['user_id']:
            send_worker_notification(worker_user['user_id'], 'Beedi Entry Recorded',
                                     f'A new beedi entry was added for you: {quantity} items, wage ₹{price * quantity:.2f}.',
                                     url_for('worker_routes.worker_dashboard'))
        # Notify all customers of this admin
        customers = db.execute('SELECT id FROM users WHERE customer_of = ?', (session['user_id'],)).fetchall()
        for cust in customers:
            db.execute('INSERT INTO notifications (user_id, message, created_at) VALUES (?, ?, ?)',
                       (cust['id'], f'New wage entry: Worker ID {worker_id}, Wage: {price * quantity}', entry_time))
        db.commit()
        flash('Beedi entry added, wage calculated, and customers notified!', 'success')
        return redirect(url_for('main.admin_dashboard'))
    return render_template('beedi_entry.html', workers=workers)


@bp.route('/log-collection', methods=['GET', 'POST'])
def log_collection():
    """Admin page to log daily collection and queue a payment + notify worker."""
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))
    db = get_db()
    workers = db.execute('SELECT * FROM workers WHERE admin_id = ?', (session['user_id'],)).fetchall()
    default_rate = 1.5
    if request.method == 'POST':
        try:
            worker_id = int(request.form['worker_id'])
            quantity = int(request.form['quantity'])
            # Use the worker's configured rate when available, otherwise fall back to submitted/default
            worker_row = db.execute('SELECT rate FROM workers WHERE id = ?', (worker_id,)).fetchone()
            if worker_row and worker_row['rate']:
                rate = float(worker_row['rate'])
            else:
                rate = float(request.form.get('rate', default_rate))
            amount = round(quantity * rate, 2)
            created_at = datetime.now().isoformat(sep=' ', timespec='seconds')

            # Create a payments record (queued/processing)
            receipt_number = generate_receipt_number()
            payment_id = db.execute('''
                INSERT INTO payments (
                    worker_id, amount, payment_method, payment_details,
                    payment_comment, receipt_number, status, payment_date, created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                worker_id,
                amount,
                'Admin Logged',
                json.dumps({'quantity': quantity, 'rate': rate}),
                f'Logged via admin collection: qty={quantity}',
                receipt_number,
                'processing',
                created_at,
                session['user_id'],
                created_at
            )).lastrowid

            # Insert into work_log and link to payment
            wl_id = db.execute('''
                INSERT INTO work_log (worker_id, quantity_collected, rate, amount, status, payment_id, processed_by_admin_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (worker_id, quantity, rate, amount, 'processing', payment_id, session['user_id'], created_at)).lastrowid

            # Notify worker via notifications table and optional push
            worker_user = db.execute('SELECT user_id FROM workers WHERE id = ?', (worker_id,)).fetchone()
            if worker_user and worker_user['user_id']:
                send_worker_notification(worker_user['user_id'], 'Digital Beedi Branch',
                                         f'Your work is approved! You will receive ₹{amount:.2f} for {quantity} beedis.',
                                         url_for('worker_routes.worker_dashboard'))
            else:
                # Fallback: add an informational notification row with NULL user
                db.execute('INSERT INTO notifications (user_id, message, created_at) VALUES (?, ?, ?)', (None, f'Work logged for worker {worker_id}: ₹{amount:.2f} for {quantity} beedis.', created_at))

            db.commit()
            flash('Work logged, payment queued and worker notified.', 'success')
            return redirect(url_for('main.admin_dashboard'))
        except Exception as e:
            db.rollback()
            flash(f'Error logging collection: {str(e)}', 'error')
            return redirect(url_for('main.log_collection'))

    return render_template('log_collection.html', workers=workers, default_rate=default_rate)

@bp.route('/wages')
def wages():
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))
    db = get_db()
    entries = db.execute('''SELECT w.name, b.price, b.quantity, b.entry_time, (b.price * b.quantity) as wage, b.is_paid, b.id, b.worker_id, b.payment_method, b.payment_details, b.payment_comment
        FROM beedi_entries b JOIN workers w ON b.worker_id = w.id WHERE b.admin_id = ? ORDER BY b.entry_time DESC''', (session['user_id'],)).fetchall()
    return render_template('wages.html', entries=entries)

@bp.route('/wages/pay/<int:entry_id>', methods=['POST'])
def mark_paid(entry_id):
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))
        
    payment_method = request.form.get('payment_method')
    payment_comment = request.form.get('payment_comment', '').strip()
    
    # Additional payment details based on method
    payment_details = {}
    if payment_method == 'UPI':
        upi_id = request.form.get('upi_id')
        if not upi_id:
            flash('UPI ID is required for UPI payments', 'error')
            return redirect(url_for('main.wages'))
        payment_details['upi_id'] = upi_id
    elif payment_method == 'Bank Transfer':
        account_number = request.form.get('account_number')
        ifsc_code = request.form.get('ifsc_code')
        if not (account_number and ifsc_code):
            flash('Account number and IFSC code are required for bank transfers', 'error')
            return redirect(url_for('main.wages'))
        payment_details['account_number'] = account_number
        payment_details['ifsc_code'] = ifsc_code
    
    db = get_db()
    try:
        # Get entry details
        entry = db.execute('''
            SELECT b.*, w.id as worker_id, w.name as worker_name, w.contact as worker_contact
            FROM beedi_entries b 
            JOIN workers w ON b.worker_id = w.id 
            WHERE b.id = ?
        ''', (entry_id,)).fetchone()
        
        if not entry:
            flash('Entry not found', 'error')
            return redirect(url_for('main.wages'))
            
        # Generate receipt number
        receipt_number = generate_receipt_number()
        payment_amount = entry['price'] * entry['quantity']
        
        # Create payment record
        payment_id = db.execute('''
            INSERT INTO payments (
                worker_id, amount, payment_method, payment_details,
                payment_comment, receipt_number, status, payment_date,
                created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            entry['worker_id'],
            payment_amount,
            payment_method,
            json.dumps(payment_details),
            payment_comment,
            receipt_number,
            'pending_confirmation',
            datetime.now().isoformat(sep=' ', timespec='seconds'),
            session['user_id']
        )).lastrowid
        
        # Update beedi entry
        db.execute('''
            UPDATE beedi_entries 
            SET is_paid = 1, 
                payment_id = ?
            WHERE id = ?
        ''', (payment_id, entry_id))
        
        # Add actionable notification for the worker (if linked to a user account)
        worker_user = db.execute('SELECT user_id FROM workers WHERE id = ?', (entry['worker_id'],)).fetchone()
        if worker_user and worker_user['user_id']:
            send_worker_notification(worker_user['user_id'], 'Payment Received',
                                     f'Payment of ₹{payment_amount:.2f} processed via {payment_method}. Receipt: {receipt_number}',
                                     url_for('main.payment_receipt', payment_id=payment_id))
        
        # Integrate Razorpay payout for UPI and Bank Transfer
        if payment_method in ['UPI', 'Bank Transfer'] and current_app.config.get('RAZORPAY_KEY_ID'):
            try:
                razorpay_client = razorpay.Client(auth=(current_app.config['RAZORPAY_KEY_ID'], current_app.config['RAZORPAY_KEY_SECRET']))
                # Create contact
                contact_data = {
                    "name": entry['worker_name'],
                    "email": f"{entry['worker_name'].replace(' ', '').lower()}@example.com",
                    "contact": entry.get('worker_contact', '9999999999'),
                    "type": "employee",
                    "reference_id": f"worker_{entry['worker_id']}"
                }
                contact = razorpay_client.contact.create(contact_data)
                # Create fund account
                if payment_method == 'UPI':
                    fund_account_data = {
                        "contact_id": contact['id'],
                        "account_type": "vpa",
                        "vpa": {
                            "address": payment_details['upi_id']
                        }
                    }
                elif payment_method == 'Bank Transfer':
                    fund_account_data = {
                        "contact_id": contact['id'],
                        "account_type": "bank_account",
                        "bank_account": {
                            "name": entry['worker_name'],
                            "ifsc": payment_details['ifsc_code'],
                            "account_number": payment_details['account_number']
                        }
                    }
                fund_account = razorpay_client.fund_account.create(fund_account_data)
                # Create payout
                payout_data = {
                    "account_number": current_app.config['RAZORPAY_ACCOUNT_NUMBER'],
                    "fund_account_id": fund_account['id'],
                    "amount": int(payment_amount * 100),
                    "currency": "INR",
                    "mode": "UPI" if payment_method == 'UPI' else "NEFT",
                    "purpose": "payout",
                    "queue_if_low_balance": True,
                    "reference_id": f"payment_{payment_id}",
                    "narration": f"Payment to {entry['worker_name']}"
                }
                payout = razorpay_client.payout.create(payout_data)
                if payout['status'] == 'processed':
                    db.execute('UPDATE payments SET status = ? WHERE id = ?', ('completed', payment_id))
            except Exception as e:
                print(f"Razorpay payout error: {e}")
        
        db.commit()
        flash(f'Payment processed successfully. Receipt number: {receipt_number}', 'success')
        return redirect(url_for('main.payment_receipt', payment_id=payment_id))
        
    except Exception as e:
        db.rollback()
        flash(f'Error processing payment: {str(e)}', 'error')
        return redirect(url_for('main.wages'))
    
    # Add notification for payment
    notification_msg = f"Payment processed for {worker['name']} via {payment_method}"
    if payment_comment:
        notification_msg += f" (Note: {payment_comment})"
        
    db.execute('''INSERT INTO notifications (user_id, message, created_at)
                  SELECT id, ?, datetime('now')
                  FROM users
                  WHERE customer_of = ?''',
               (notification_msg, session['user_id']))
    
    db.commit()
    flash(f'Payment processed successfully via {payment_method}!', 'success')
    return redirect(url_for('main.wages'))

@bp.route('/customer-wages')
def customer_wages():
    if session.get('role') != 'customer':
        return redirect(url_for('auth.admin_login'))
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    admin_id = user['customer_of']
    entries = db.execute('''SELECT w.name, b.price, b.quantity, b.entry_time, (b.price * b.quantity) as wage
        FROM beedi_entries b JOIN workers w ON b.worker_id = w.id WHERE b.admin_id = ? ORDER BY b.entry_time DESC''', (admin_id,)).fetchall()
    return render_template('wages.html', entries=entries)

@bp.route('/notifications')
def notifications():
    if 'user_id' not in session:
        return redirect(url_for('auth.admin_login'))
    db = get_db()
    notes = db.execute('SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC', (session['user_id'],)).fetchall()
    # Mark all as read
    db.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ?', (session['user_id'],))
    db.commit()
    return render_template('notifications.html', notifications=notes)


@bp.route('/notifications/mark-read/<int:note_id>', methods=['POST'])
def mark_notification_read(note_id):
    """API endpoint to mark a single notification as read for the current user."""
    if 'user_id' not in session:
        return jsonify({'error': 'authentication required'}), 401
    db = get_db()
    note = db.execute('SELECT * FROM notifications WHERE id = ?', (note_id,)).fetchone()
    if not note:
        return jsonify({'error': 'not found'}), 404
    # ownership check: allow if NULL (system) or matching user
    owner = note['user_id'] if 'user_id' in note.keys() else None
    if owner and owner != session['user_id']:
        return jsonify({'error': 'forbidden'}), 403

    # ensure is_read column exists
    cols = [r['name'] for r in db.execute("PRAGMA table_info(notifications)").fetchall()]
    if 'is_read' not in cols:
        try:
            db.execute('ALTER TABLE notifications ADD COLUMN is_read INTEGER DEFAULT 0')
            db.commit()
        except Exception:
            pass

    try:
        db.execute('UPDATE notifications SET is_read = 1 WHERE id = ?', (note_id,))
        db.commit()
        return jsonify({'ok': True}), 200
    except Exception:
        db.rollback()
        return jsonify({'error': 'update failed'}), 500


@bp.route('/notifications/clear', methods=['POST'])
def clear_notifications():
    """Mark all notifications as read for the current user."""
    if 'user_id' not in session:
        return jsonify({'error': 'authentication required'}), 401
    db = get_db()
    # ensure is_read column exists
    cols = [r['name'] for r in db.execute("PRAGMA table_info(notifications)").fetchall()]
    if 'is_read' not in cols:
        try:
            db.execute('ALTER TABLE notifications ADD COLUMN is_read INTEGER DEFAULT 0')
            db.commit()
        except Exception:
            pass
    try:
        db.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ?', (session['user_id'],))
        db.commit()
        return jsonify({'ok': True}), 200
    except Exception:
        db.rollback()
        return jsonify({'error': 'update failed'}), 500

@bp.route('/todos', methods=['GET', 'POST'])
def todos():
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))
    db = get_db()
    if request.method == 'POST':
        task = request.form['task']
        db.execute('INSERT INTO todos (admin_id, task, created_at) VALUES (?, ?, ?)',
                   (session['user_id'], task, datetime.now().isoformat(sep=' ', timespec='seconds')))
        db.commit()
        flash('Task added!', 'success')
        return redirect(url_for('main.todos'))
    todos = db.execute('SELECT * FROM todos WHERE admin_id = ? ORDER BY is_done, created_at DESC', (session['user_id'],)).fetchall()
    return render_template('todos.html', todos=todos)

@bp.route('/todos/complete/<int:todo_id>', methods=['POST'])
def complete_todo(todo_id):
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))
    db = get_db()
    db.execute('UPDATE todos SET is_done = 1 WHERE id = ? AND admin_id = ?', (todo_id, session['user_id']))
    db.commit()
    flash('Task marked as done!', 'success')
    return redirect(url_for('main.todos'))

@bp.route('/wages/bulk-payment', methods=['POST'])
def bulk_payment():
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))
    entry_ids = request.form.getlist('entry_ids[]')
    payment_method = request.form.get('payment_method')
    
    if not entry_ids or not payment_method:
        flash('Please select entries and payment method for bulk payment', 'error')
        return redirect(url_for('main.wages'))
    
    db = get_db()
    timestamp = datetime.now().isoformat(sep=' ', timespec='seconds')
    payment_info = {
        'method': payment_method,
        'details': {},
        'timestamp': timestamp,
        'admin_username': session.get('username', 'Unknown'),
        'bulk_payment': True
    }
    
    try:
        for entry_id in entry_ids:
            db.execute('''UPDATE beedi_entries 
                         SET is_paid = 1, 
                             payment_method = ?, 
                             payment_details = ?,
                             payment_comment = ?
                         WHERE id = ? AND admin_id = ?''', 
                      (payment_method, str(payment_info), 
                       f'Bulk payment processed on {timestamp}', 
                       entry_id, session['user_id']))
        
        db.commit()
        flash(f'Successfully processed {len(entry_ids)} payments via {payment_method}!', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Error processing bulk payments: {str(e)}', 'error')
    
    return redirect(url_for('main.wages'))


@bp.route('/wages/unpay/<int:entry_id>', methods=['POST'])
@admin_required
def mark_unpaid(entry_id):
    db = get_db()
    try:
        # Find the entry and linked payment
        entry = db.execute('SELECT * FROM beedi_entries WHERE id = ? AND admin_id = ?', (entry_id, session['user_id'])).fetchone()
        if not entry:
            flash('Entry not found or permission denied', 'error')
            return redirect(url_for('main.wages'))

        payment_id = entry['payment_id'] if 'payment_id' in entry.keys() else None
        # Mark entry unpaid and clear payment linkage
        db.execute('UPDATE beedi_entries SET is_paid = 0, payment_id = NULL WHERE id = ?', (entry_id,))

        # If a payment row exists, mark it reversed for an audit trail
        if payment_id:
            db.execute('UPDATE payments SET status = ?, payment_comment = COALESCE(payment_comment, "") || ? WHERE id = ?',
                       ('reversed', f' | Reversed by admin {session.get("username")}', payment_id))

        # Insert actionable notification for worker if they have a linked user account
        worker_user = db.execute('SELECT user_id FROM workers WHERE id = ?', (entry['worker_id'],)).fetchone()
        message = f'Payment for entry {entry_id} has been marked unpaid by admin.'
        if worker_user and worker_user['user_id']:
            send_worker_notification(worker_user['user_id'], 'Payment Marked Unpaid', message, url_for('main.wages'))
        else:
            db.execute('INSERT INTO notifications (user_id, message, created_at) VALUES (?, ?, ?)',
                       (None, message, datetime.now().isoformat(sep=' ', timespec='seconds')))

        db.commit()
        flash('Entry marked as unpaid and payment reversed (audit recorded).', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Error marking unpaid: {str(e)}', 'error')
    return redirect(url_for('main.wages'))

@bp.route('/payment-analytics')
def payment_analytics():
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))
    
    db = get_db()
    # use timedelta imported from datetime at top of this file
    thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    # Get basic statistics
    stats = db.execute('''
        SELECT 
            COUNT(*) as total_entries,
            SUM(CASE WHEN is_paid = 1 THEN 1 ELSE 0 END) as paid_entries,
            SUM(CASE WHEN is_paid = 1 THEN price * quantity ELSE 0 END) as total_paid,
            AVG(CASE WHEN is_paid = 1 THEN price * quantity ELSE NULL END) as avg_payment
        FROM beedi_entries 
        WHERE admin_id = ? AND entry_time >= ?
    ''', (session['user_id'], thirty_days_ago)).fetchone()

    # Get payment methods distribution
    methods = db.execute('''
        SELECT payment_method, COUNT(*) as count
        FROM beedi_entries
        WHERE admin_id = ? AND is_paid = 1
        GROUP BY payment_method
    ''', (session['user_id'],)).fetchall()

    # Get daily payment trends
    trends = db.execute('''
        SELECT date(entry_time) as day, SUM(price * quantity) as total
        FROM beedi_entries
        WHERE admin_id = ? AND is_paid = 1 AND entry_time >= ?
        GROUP BY date(entry_time)
        ORDER BY day
    ''', (session['user_id'], thirty_days_ago)).fetchall()

    # Get top workers
    top_workers = db.execute('''
        SELECT 
            w.name,
            SUM(b.price * b.quantity) as total_earnings,
            SUM(b.quantity) as total_beedis,
            ROUND(AVG(CASE WHEN b.is_paid = 1 THEN 100 ELSE 0 END), 2) as payment_ratio,
            (
                SELECT payment_method
                FROM beedi_entries b2
                WHERE b2.worker_id = w.id AND b2.is_paid = 1
                GROUP BY payment_method
                ORDER BY COUNT(*) DESC
                LIMIT 1
            ) as preferred_method
        FROM workers w
        LEFT JOIN beedi_entries b ON w.id = b.worker_id
        WHERE w.admin_id = ?
        GROUP BY w.id, w.name
        ORDER BY total_earnings DESC
        LIMIT 10
    ''', (session['user_id'],)).fetchall()

    # Get recent payments
    recent_payments = db.execute('''
        SELECT 
            b.entry_time as timestamp,
            w.name as worker_name,
            (b.price * b.quantity) as amount,
            b.payment_method as method
        FROM beedi_entries b
        JOIN workers w ON b.worker_id = w.id
        WHERE b.admin_id = ? AND b.is_paid = 1
        ORDER BY b.entry_time DESC
        LIMIT 10
    ''', (session['user_id'],)).fetchall()

    total_entries = stats['total_entries'] or 0
    paid_entries = stats['paid_entries'] or 0
    total_paid = stats['total_paid'] or 0
    avg_payment = stats['avg_payment'] or 0

    return render_template('payment_analytics.html',
        total_amount=total_paid,
        paid_count=paid_entries,
        pending_count=max(total_entries - paid_entries, 0),
        average_payment=round(avg_payment, 2),
        payment_methods_labels=[m['payment_method'] for m in methods],
        payment_methods_data=[m['count'] for m in methods],
        payment_trends_labels=[t['day'] for t in trends],
        payment_trends_data=[float(t['total']) for t in trends],
        top_workers=top_workers,
        recent_payments=recent_payments
    )

@bp.route('/payment-schedule')
def payment_schedule():
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))
        
    db = get_db()
    
    # Get all payment schedules
    schedules = db.execute('''
        SELECT 
            ps.*,
            w.name as worker_name,
            CASE 
                WHEN ps.status = 'pending' AND date(ps.scheduled_date) < date('now') 
                THEN 'overdue'
                ELSE ps.status 
            END as display_status
        FROM payment_schedules ps
        JOIN workers w ON ps.worker_id = w.id
        WHERE ps.admin_id = ?
        ORDER BY ps.scheduled_date ASC
    ''', (session['user_id'],)).fetchall()
    
    # Get all workers for the schedule form
    workers = db.execute('SELECT id, name FROM workers WHERE admin_id = ?', 
                        (session['user_id'],)).fetchall()
    
    # Prepare calendar events
    calendar_events = []
    for schedule in schedules:
        event_color = {
            'pending': '#ffc107',  # warning yellow
            'completed': '#198754', # success green
            'overdue': '#dc3545'    # danger red
        }.get(schedule['status'], '#0d6efd')  # default blue
        
        calendar_events.append({
            'title': f"₹{schedule['amount']} - {schedule['worker_name']}",
            'start': schedule['scheduled_date'],
            'backgroundColor': event_color,
            'url': f"/payment-schedule/{schedule['id']}"
        })
    
    return render_template('payment_schedule.html', 
                         schedules=schedules,
                         workers=workers,
                         calendar_events=calendar_events)

@bp.route('/payment-schedule', methods=['POST'])
def create_payment_schedule():
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))
        
    worker_id = request.form.get('worker_id')
    amount = request.form.get('amount')
    scheduled_date = request.form.get('scheduled_date')
    payment_method = request.form.get('payment_method')
    notes = request.form.get('notes')
    send_reminder = bool(request.form.get('send_reminder'))
    
    db = get_db()
    db.execute('''
        INSERT INTO payment_schedules 
        (worker_id, admin_id, amount, scheduled_date, payment_method, notes, send_reminder)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (worker_id, session['user_id'], amount, scheduled_date, payment_method, notes, send_reminder))
    db.commit()
    
    flash('Payment schedule created successfully!', 'success')
    return redirect(url_for('main.payment_schedule'))

@bp.route('/payment-schedule/<int:schedule_id>')
def get_payment_schedule(schedule_id):
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
        
    db = get_db()
    schedule = db.execute('''
        SELECT ps.*, w.name as worker_name
        FROM payment_schedules ps
        JOIN workers w ON ps.worker_id = w.id
        WHERE ps.id = ? AND ps.admin_id = ?
    ''', (schedule_id, session['user_id'])).fetchone()
    
    if not schedule:
        return jsonify({'error': 'Not found'}), 404
        
    return jsonify(dict(schedule))

@bp.route('/payment-schedule/<int:schedule_id>/edit', methods=['POST'])
def edit_payment_schedule(schedule_id):
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))
        
    db = get_db()
    db.execute('''
        UPDATE payment_schedules
        SET worker_id = ?,
            amount = ?,
            scheduled_date = ?,
            payment_method = ?,
            notes = ?,
            send_reminder = ?
        WHERE id = ? AND admin_id = ?
    ''', (
        request.form['worker_id'],
        request.form['amount'],
        request.form['scheduled_date'],
        request.form['payment_method'],
        request.form['notes'],
        bool(request.form.get('send_reminder')),
        schedule_id,
        session['user_id']
    ))
    db.commit()
    
    flash('Payment schedule updated successfully!', 'success')
    return redirect(url_for('main.payment_schedule'))

@bp.route('/payment-schedule/<int:schedule_id>/delete', methods=['POST'])
def delete_payment_schedule(schedule_id):
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
        
    db = get_db()
    db.execute('DELETE FROM payment_schedules WHERE id = ? AND admin_id = ?', 
               (schedule_id, session['user_id']))
    db.commit()
    
    return jsonify({'success': True})

@bp.route('/payment-schedule/<int:schedule_id>/process', methods=['POST'])
def process_scheduled_payment(schedule_id):
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
        
    db = get_db()
    
    # Get schedule details
    schedule = db.execute('''
        SELECT ps.*, w.name as worker_name
        FROM payment_schedules ps
        JOIN workers w ON ps.worker_id = w.id
        WHERE ps.id = ? AND ps.admin_id = ?
    ''', (schedule_id, session['user_id'])).fetchone()
    
    if not schedule:
        return jsonify({'error': 'Schedule not found'}), 404
    
    try:
        # Create beedi entry for the payment
        payment_info = {
            'method': schedule['payment_method'],
            'details': {},
            'timestamp': datetime.now().isoformat(sep=' ', timespec='seconds'),
            'admin_username': session.get('username', 'Unknown'),
            'scheduled_payment': True,
            'schedule_id': schedule_id
        }
        
        # Update schedule status
        db.execute('''
            UPDATE payment_schedules 
            SET status = 'completed' 
            WHERE id = ?''', (schedule_id,))
        
        # Notify the worker (actionable) if they have a linked user account; otherwise notify admin
        worker_user = db.execute('SELECT user_id FROM workers WHERE id = ?', (schedule['worker_id'],)).fetchone()
        message = f"Scheduled payment of ₹{schedule['amount']} processed for {schedule['worker_name']}"
        if worker_user and worker_user['user_id']:
            send_worker_notification(worker_user['user_id'], 'Scheduled Payment Processed', message, url_for('main.payment_schedule'))
        else:
            db.execute('''INSERT INTO notifications (user_id, message, created_at) 
                         VALUES (?, ?, datetime('now'))''',
                       (session['user_id'], message))
        
        db.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/reconciliation')
def payment_reconciliation():
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))
    
    db = get_db()
    
    # Get reconciliation summary
    summary = db.execute('''
        SELECT 
            SUM(expected_amount) as total_expected,
            SUM(actual_amount) as total_paid,
            COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_review
        FROM payment_reconciliation
        WHERE admin_id = ?
    ''', (session['user_id'],)).fetchone()
    
    # Get reconciliation items
    items = db.execute('''
        SELECT 
            r.*,
            w.name as worker_name,
            (r.expected_amount - r.actual_amount) as difference,
            CASE 
                WHEN r.status = 'verified' THEN 'success'
                WHEN r.status = 'pending' AND date(r.date) < date('now') THEN 'warning'
                WHEN r.status = 'pending' THEN 'info'
                ELSE 'secondary'
            END as status_color
        FROM payment_reconciliation r
        JOIN workers w ON r.worker_id = w.id
        WHERE r.admin_id = ?
        ORDER BY r.date DESC
    ''', (session['user_id'],)).fetchall()
    
    return render_template('payment_reconciliation.html',
        total_expected=summary['total_expected'] or 0,
        total_paid=summary['total_paid'] or 0,
        discrepancy=(summary['total_expected'] or 0) - (summary['total_paid'] or 0),
        pending_review=summary['pending_review'] or 0,
        reconciliation_items=items
    )

@bp.route('/reconciliation/details/<int:item_id>')
def reconciliation_details(item_id):
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    db = get_db()
    
    # Get reconciliation details
    item = db.execute('''
        SELECT r.*, w.name as worker_name, w.id as worker_id, w.contact as worker_contact
        FROM payment_reconciliation r
        JOIN workers w ON r.worker_id = w.id
        WHERE r.id = ? AND r.admin_id = ?
    ''', (item_id, session['user_id'])).fetchone()
    
    if not item:
        return jsonify({'error': 'Item not found'}), 404
    
    # Get payment history
    payments = db.execute('''
        SELECT 
            created_at as date,
            amount,
            payment_method as method,
            status
        FROM payment_tracking
        WHERE reconciliation_id = ?
        ORDER BY created_at DESC
    ''', (item_id,)).fetchall()
    
    return jsonify({
        'worker_name': item['worker_name'],
        'worker_id': item['worker_id'],
        'worker_contact': item['worker_contact'],
        'expected_amount': item['expected_amount'],
        'actual_amount': item['actual_amount'],
        'date': item['date'],
        'notes': item['notes'],
        'payment_history': [dict(p) for p in payments]
    })

@bp.route('/reconciliation/verify/<int:item_id>', methods=['POST'])
def verify_reconciliation(item_id):
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    db = get_db()
    try:
        db.execute('''
            UPDATE payment_reconciliation
            SET status = 'verified',
                verified_at = datetime('now')
            WHERE id = ? AND admin_id = ?
        ''', (item_id, session['user_id']))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/reconciliation/add-note', methods=['POST'])
def add_reconciliation_note():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    item_id = request.form.get('item_id')
    note = request.form.get('note')
    
    if not all([item_id, note]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    db = get_db()
    try:
        db.execute('''
            UPDATE payment_reconciliation
            SET notes = CASE 
                WHEN notes IS NULL THEN ?
                ELSE notes || char(10) || ?
            END
            WHERE id = ? AND admin_id = ?
        ''', (note, note, item_id, session['user_id']))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/reconciliation/reconcile-all', methods=['POST'])
def reconcile_all():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    db = get_db()
    try:
        # Get all pending reconciliation items
        items = db.execute('''
            SELECT id, worker_id, expected_amount
            FROM payment_reconciliation
            WHERE status = 'pending' AND admin_id = ?
        ''', (session['user_id'],)).fetchall()
        
        for item in items:
            # Check actual payments
            actual_amount = db.execute('''
                SELECT COALESCE(SUM(amount), 0) as total
                FROM payment_tracking
                WHERE reconciliation_id = ?
            ''', (item['id'],)).fetchone()['total']
            
            # Update reconciliation record
            db.execute('''
                UPDATE payment_reconciliation
                SET actual_amount = ?,
                    status = CASE 
                        WHEN ? = expected_amount THEN 'verified'
                        ELSE 'pending'
                    END,
                    verified_at = CASE 
                        WHEN ? = expected_amount THEN datetime('now')
                        ELSE NULL
                    END
                WHERE id = ?
            ''', (actual_amount, actual_amount, actual_amount, item['id']))
        
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/reconciliation/<action>', methods=['POST'])
def batch_reconciliation(action):
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    items = request.json.get('items', [])
    if not items:
        return jsonify({'error': 'No items selected'}), 400
    
    db = get_db()
    try:
        if action == 'verify':
            db.execute('''
                UPDATE payment_reconciliation
                SET status = 'verified',
                    verified_at = datetime('now')
                WHERE id IN ({}) AND admin_id = ?
            '''.format(','.join('?' * len(items))), (*items, session['user_id']))
            
        elif action == 'mark-paid':
            for item_id in items:
                db.execute('''
                    INSERT INTO payment_tracking (
                        reconciliation_id, amount, payment_method, status, notes
                    ) VALUES (?, ?, 'Cash', 'completed', 'Marked as paid via batch action')
                ''', (item_id, db.execute('SELECT expected_amount FROM payment_reconciliation WHERE id = ?', 
                                        (item_id,)).fetchone()['expected_amount']))
            
        elif action == 'export':
            # Return export data
            export_data = db.execute('''
                SELECT 
                    r.date,
                    w.name as worker_name,
                    r.expected_amount,
                    r.actual_amount,
                    r.status,
                    r.notes
                FROM payment_reconciliation r
                JOIN workers w ON r.worker_id = w.id
                WHERE r.id IN ({})
            '''.format(','.join('?' * len(items))), items).fetchall()
            
            return jsonify({
                'success': True,
                'data': [dict(row) for row in export_data]
            })
        
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/receipt/<int:entry_id>')
def generate_receipt(entry_id):
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))

    db = get_db()
    # Get all necessary information for the receipt
    entry = db.execute('''
        SELECT b.*, w.name, w.contact, w.id as worker_id, 
               (b.price * b.quantity) as wage,
               b.payment_method, b.payment_details, b.payment_comment
        FROM beedi_entries b 
        JOIN workers w ON b.worker_id = w.id 
        WHERE b.id = ? AND b.admin_id = ?
    ''', (entry_id, session['user_id'])).fetchone()

    if not entry or not entry['is_paid']:
        flash('Invalid entry or payment not processed yet', 'error')
        return redirect(url_for('main.wages'))

    # Format for the template
    receipt_data = {
        'worker': {
            'name': entry['name'],
            'id': entry['worker_id'],
            'contact': entry['contact']
        },
        'entry_id': entry_id,
        'quantity': entry['quantity'],
        'price': entry['price'],
        'wage': entry['wage'],
        'entry_time': entry['entry_time'],
        'payment_method': entry['payment_method'],
        'payment_info': eval(entry['payment_details']) if entry['payment_details'] else {},
        'payment_comment': entry['payment_comment'],
        'receipt_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'receipt_no': f"RCP-{entry_id:06d}",
        'print_view': request.args.get('format') == 'pdf'
    }

    # Generate receipt
    # Add print-specific styling
    receipt_data['print_view'] = True
    return render_template('receipt.html', **receipt_data)

@bp.route('/worker/<int:worker_id>/edit', methods=['GET'])
def edit_worker(worker_id):
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))
    db = get_db()
    worker = db.execute('SELECT * FROM workers WHERE id = ?', (worker_id,)).fetchone()
    if not worker:
        flash('Worker not found', 'error')
        return redirect(url_for('main.index'))
    return render_template('edit_worker.html', worker=worker)


@bp.route('/worker/<int:worker_id>/update', methods=['POST'])
def update_worker(worker_id):
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))
    db = get_db()

    # determine which columns exist in workers table so updates are safe
    cols = [r['name'] for r in db.execute("PRAGMA table_info(workers)").fetchall()]

    fields = ['name', 'age', 'contact', 'address', 'aadhar', 'bank_account', 'ifsc_code', 'upi_id', 'rate', 'preferred_payment_method']
    updates = []
    params = []
    for f in fields:
        if f in cols and f in request.form:
            updates.append(f + ' = ?')
            params.append(request.form.get(f))

    if updates:
        params.append(worker_id)
        db.execute(f"UPDATE workers SET {', '.join(updates)} WHERE id = ?", params)
        db.commit()
        flash('Worker details updated successfully', 'success')
    else:
        flash('No updatable fields found or missing columns in DB', 'warning')

    return redirect(url_for('main.edit_worker', worker_id=worker_id))


@bp.route('/worker/<int:worker_id>/make-payment', methods=['POST'])
def make_worker_payment(worker_id):
    if session.get('role') != 'admin':
        return redirect(url_for('auth.login'))

    try:
        amount = float(request.form.get('amount', 0))
        payment_method = request.form.get('payment_method')
        payment_comment = request.form.get('payment_comment', '').strip()

        if amount <= 0:
            flash('Amount must be greater than 0', 'error')
            return redirect(url_for('main.worker_details', worker_id=worker_id))
            
        if not payment_method:
            flash('Please select a payment method', 'error')
            return redirect(url_for('main.worker_details', worker_id=worker_id))

        payment_details = {}
        db = get_db()
        
        if payment_method == 'UPI':
            upi = request.form.get('upi_id') or None
            if not upi:
                # if worker has stored upi, use that
                w = db.execute('SELECT upi_id FROM workers WHERE id = ?', (worker_id,)).fetchone()
                upi = w['upi_id'] if w and w.get('upi_id') else None
            if not upi:
                flash('UPI ID is required for UPI payments', 'error')
                return redirect(url_for('main.worker_details', worker_id=worker_id))
            if '@' not in upi:
                flash('Please enter a valid UPI ID (should contain @)', 'error')
                return redirect(url_for('main.worker_details', worker_id=worker_id))
            payment_details['upi_id'] = upi
            
        elif payment_method == 'Bank Transfer':
            acc = request.form.get('account_number') or None
            ifsc = request.form.get('ifsc_code') or None
            if not (acc and ifsc):
                # fallback to stored bank data
                w = db.execute('SELECT bank_account, ifsc_code FROM workers WHERE id = ?', (worker_id,)).fetchone()
                if w:
                    acc = acc or w.get('bank_account')
                    ifsc = ifsc or w.get('ifsc_code')
            if not (acc and ifsc):
                flash('Account number and IFSC code are required for bank transfers', 'error')
                return redirect(url_for('main.worker_details', worker_id=worker_id))
            if not ifsc.strip().upper().replace(" ", "").match(r'^[A-Z]{4}0[A-Z0-9]{6}$'):
                flash('Please enter a valid IFSC code (e.g., HDFC0000123)', 'error')
                return redirect(url_for('main.worker_details', worker_id=worker_id))
            payment_details['account_number'] = acc
            payment_details['ifsc_code'] = ifsc.strip().upper()
            
        elif payment_method == 'Cash':
            if not payment_comment:
                flash('Please note the denominations given in cash payment', 'warning')

        db = get_db()
        # insert into payments table
        db.execute('''
            INSERT INTO payments (worker_id, amount, payment_method, payment_details, status, payment_date)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        ''', (worker_id, amount, payment_method, json.dumps({'details': payment_details}), 'completed'))
        db.commit()

        # Optionally save payment details to worker record if admin chose to
        save_pref = request.form.get('save_payment_details')
        if save_pref == 'on':
            update_cols = []
            update_params = []
            if payment_method == 'UPI' and payment_details.get('upi_id'):
                update_cols.append('upi_id = ?')
                update_params.append(payment_details['upi_id'])
            if payment_method == 'Bank Transfer' and payment_details.get('account_number'):
                update_cols.append('bank_account = ?')
                update_params.append(payment_details['account_number'])
                update_cols.append('ifsc_code = ?')
                update_params.append(payment_details['ifsc_code'])
            if update_cols:
                update_params.append(worker_id)
                db.execute(f"UPDATE workers SET {', '.join(update_cols)} WHERE id = ?", update_params)
                db.commit()

        # Notify the worker about the payment
        worker_user = db.execute('SELECT user_id FROM workers WHERE id = ?', (worker_id,)).fetchone()
        if worker_user and worker_user['user_id']:
            send_worker_notification(worker_user['user_id'], 'Payment Received',
                                     f'You have received ₹{amount:.2f} via {payment_method}.')

        flash('Payment recorded successfully', 'success')
    except Exception as e:
        flash(f'Error recording payment: {str(e)}', 'error')

    return redirect(url_for('main.worker_details', worker_id=worker_id))


@bp.route('/worker/payment-details/<int:worker_id>')
def get_worker_payment_details(worker_id):
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    # Get worker's last used payment method and details from recent paid entries
    last_payment = db.execute('''
        SELECT payment_method, payment_details
        FROM payments
        WHERE worker_id = ? AND status IN ('completed', 'paid')
        ORDER BY payment_date DESC LIMIT 1
    ''', (worker_id,)).fetchone()

    if last_payment and last_payment['payment_method']:
        details = {}
        try:
            details = json.loads(last_payment['payment_details']) if last_payment['payment_details'] else {}
        except Exception:
            try:
                details = eval(last_payment['payment_details']) if last_payment['payment_details'] else {}
            except Exception:
                details = {}

        return jsonify({
            'payment_method': last_payment['payment_method'],
            'payment_details': details
        })

    # If no last payment, fall back to worker stored payment info (if columns exist)
    cols = [r['name'] for r in db.execute("PRAGMA table_info(workers)").fetchall()]
    stored = {}
    method = None
    if 'upi_id' in cols:
        row = db.execute('SELECT upi_id FROM workers WHERE id = ?', (worker_id,)).fetchone()
        if row and row.get('upi_id'):
            stored['details'] = {'upi_id': row['upi_id']}
            method = 'UPI'
    if not method and 'bank_account' in cols:
        row = db.execute('SELECT bank_account, ifsc_code FROM workers WHERE id = ?', (worker_id,)).fetchone()
        if row and (row.get('bank_account') or row.get('ifsc_code')):
            stored['details'] = {'account_number': row.get('bank_account'), 'ifsc_code': row.get('ifsc_code')}
            method = 'Bank Transfer'

    if method:
        return jsonify({'payment_method': method, 'payment_details': stored})

    return jsonify({'payment_method': None, 'payment_details': {}})

@bp.route('/health')
def health():
    return jsonify({'status': 'ok', 'message': 'Server is running'}), 200