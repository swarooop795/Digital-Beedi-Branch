from flask import Blueprint, request, render_template, redirect, url_for, flash, session
from app.models.database import get_db

bp = Blueprint('worker_routes', __name__)

@bp.route('/workers')
def workers():
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))
    db = get_db()
    # Include linked username (if any) so the template can pre-fill/reset credentials
    workers = db.execute('''
        SELECT w.*, u.username as linked_username
        FROM workers w
        LEFT JOIN users u ON w.user_id = u.id
        WHERE w.admin_id = ?
    ''', (session['user_id'],)).fetchall()
    return render_template('workers.html', workers=workers)

@bp.route('/worker-dashboard')
def worker_dashboard():
    if session.get('role') != 'worker':
        return redirect(url_for('auth.worker_login'))
    
    db = get_db()
    worker_id = session['worker_id']
    
    # Get worker details
    worker = db.execute('SELECT * FROM workers WHERE id = ?', (worker_id,)).fetchone()
    
    # Get recent payments
    payments = db.execute('''
        SELECT * FROM payments
        WHERE worker_id = ?
        ORDER BY payment_date DESC
        LIMIT 10
    ''', (worker_id,)).fetchall()
    
    # Get work history
    work_history = db.execute('''
        SELECT * FROM beedi_entries
        WHERE worker_id = ?
        ORDER BY entry_time DESC
        LIMIT 15
    ''', (worker_id,)).fetchall()

    # Get admin-logged daily collections (work_log)
    work_logs = db.execute('''
        SELECT wl.*, p.status as payment_status, p.receipt_number
        FROM work_log wl
        LEFT JOIN payments p ON wl.payment_id = p.id
        WHERE wl.worker_id = ?
        ORDER BY wl.created_at DESC
        LIMIT 20
    ''', (worker_id,)).fetchall()
    
    # Get recent notifications for the logged-in user (if any)
    try:
        notifications = db.execute('''
            SELECT * FROM notifications
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 20
        ''', (session.get('user_id'),)).fetchall()
    except Exception:
        notifications = []

    # Get raw material inventory (e.g., beedi leaves) to show on worker dashboard
    try:
        raw_materials = db.execute('SELECT * FROM inventory WHERE type_of_item = ?', ('raw_material',)).fetchall()
    except Exception:
        raw_materials = []

    return render_template('worker_profile.html',
                         worker=worker,
                         payments=payments,
                         work_history=work_history,
                         work_logs=work_logs,
                         notifications=notifications,
                         raw_materials=raw_materials)



@bp.route('/notifications/open/<int:note_id>')
def open_notification(note_id):
    """Mark a notification as read (if it belongs to the current user) and redirect to its URL if present."""
    if 'user_id' not in session:
        return redirect(url_for('auth.worker_login'))
    db = get_db()
    note = db.execute('SELECT * FROM notifications WHERE id = ?', (note_id,)).fetchone()
    if not note:
        flash('Notification not found', 'error')
        return redirect(url_for('worker_routes.worker_dashboard'))

    # Ensure current user owns the notification (or allow if user_id is NULL)
    try:
        owner_id = note['user_id']
    except Exception:
        owner_id = None

    if owner_id and owner_id != session.get('user_id'):
        flash('Permission denied for notification', 'error')
        return redirect(url_for('worker_routes.worker_dashboard'))

    # Ensure is_read column exists; if not, add it (safe ALTER)
    cols = [r['name'] for r in db.execute("PRAGMA table_info(notifications)").fetchall()]
    if 'is_read' not in cols:
        try:
            db.execute('ALTER TABLE notifications ADD COLUMN is_read INTEGER DEFAULT 0')
            db.commit()
        except Exception:
            # ignore -- can't alter, continue
            pass

    try:
        db.execute('UPDATE notifications SET is_read = 1 WHERE id = ?', (note_id,))
        db.commit()
    except Exception:
        db.rollback()

    # Redirect to the stored url (if present), else back to dashboard
    note_url = note.get('url') if isinstance(note, dict) else note['url'] if note and 'url' in note.keys() else None
    if note_url:
        return redirect(note_url)
    return redirect(url_for('worker_routes.worker_dashboard'))

@bp.route('/add-worker', methods=['GET', 'POST'])
def add_worker():
    if session.get('role') != 'admin':
        return redirect(url_for('auth.admin_login'))
    if request.method == 'POST':
        name = request.form['name']
        contact = request.form['contact']
        address = request.form['address']
        aadhar_number = request.form['aadhar_number']
        bank_account = request.form.get('bank_account')
        contractor = request.form.get('contractor')
        db = get_db()
        cursor = db.execute('INSERT INTO workers (name, contact, address, aadhar_number, admin_id, bank_account, contractor) VALUES (?, ?, ?, ?, ?, ?, ?)',
                   (name, contact, address, aadhar_number, session['user_id'], bank_account, contractor))
        db.commit()

        # Optionally create login credentials for the worker if admin provided them
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if username:
            # Create a users record and link it to the worker row via workers.user_id
            try:
                # prefer creating with role 'worker' if schema allows it
                from app.models.user import User
                # if password not provided (OTP flow), create a random password
                if not password:
                    import uuid
                    password = str(uuid.uuid4())[:12]
                User.create_user(username, password, 'worker')
            except Exception:
                # fallback: create as 'customer' if 'worker' role isn't allowed in the users CHECK
                try:
                    from app.models.user import User
                    User.create_user(username, password, 'customer')
                except Exception as e:
                    flash('Could not create login for worker: ' + str(e), 'warning')
            else:
                # fetch the created user id and update the worker row
                user = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
                if user:
                    # get the worker id we just created
                    worker_row = db.execute('SELECT id FROM workers WHERE name = ? AND admin_id = ? ORDER BY id DESC LIMIT 1',
                                            (name, session['user_id'])).fetchone()
                    if worker_row:
                        try:
                            db.execute('UPDATE workers SET user_id = ? WHERE id = ?', (user['id'], worker_row['id']))
                            db.commit()
                        except Exception:
                            # non-fatal: mapping didn't succeed
                            pass

        flash('Worker added successfully!', 'success')
        return redirect(url_for('worker_routes.workers'))
    return render_template('add_worker.html')