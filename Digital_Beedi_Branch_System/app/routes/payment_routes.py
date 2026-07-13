from flask import render_template, session, redirect, url_for, flash, request, jsonify
from app.models.database import get_db
from app.utils.notifications import send_worker_notification
from datetime import datetime
import json

# reuse main blueprint and helpers to avoid duplicate blueprint registrations
from app.routes.main_routes import bp as main_bp, admin_required, generate_receipt_number

bp = main_bp

@bp.route('/payment/<int:payment_id>/receipt')
def payment_receipt(payment_id):
    if session.get('role') != 'admin':
        return redirect(url_for('auth.login'))
    
    db = get_db()
    payment = db.execute('''
        SELECT p.*, w.name as worker_name, w.contact
        FROM payments p
        JOIN workers w ON p.worker_id = w.id
        WHERE p.id = ?
    ''', (payment_id,)).fetchone()
    
    if not payment:
        flash('Payment not found', 'error')
        return redirect(url_for('main.index'))
    
    # Convert payment to dict for easier template access
    payment_dict = dict(payment)
    
    # Parse payment details JSON
    if payment_dict.get('payment_details'):
        try:
            payment_dict['details'] = json.loads(payment_dict['payment_details'])
        except:
            payment_dict['details'] = {}
    
    # Create worker dict for template using the converted dict
    worker = {
        'id': payment_dict.get('worker_id'),
        'name': payment_dict.get('worker_name'),
        'contact': payment_dict.get('contact')
    }
    
    return render_template('payment_receipt.html', payment=payment_dict, worker=worker)

@bp.route('/payment/<int:payment_id>/confirm', methods=['POST'])
@admin_required
def confirm_payment(payment_id):
    db = get_db()
    
    # Check if payment exists and is pending confirmation
    payment = db.execute('SELECT * FROM payments WHERE id = ?', (payment_id,)).fetchone()
    if not payment:
        return jsonify({'success': False, 'error': 'Payment not found'})
    
    if payment['status'] != 'pending_confirmation':
        return jsonify({'success': False, 'error': 'Payment is not pending confirmation'})
    
    try:
        # Update payment status
        db.execute('''
            UPDATE payments 
            SET status = 'completed',
                confirmed_by = ?,
                confirmed_at = ?
            WHERE id = ?
        ''', (session['user_id'], datetime.now().isoformat(), payment_id))
        
        # Add actionable notification for the worker (if linked to a user account)
        worker_user = db.execute('SELECT user_id FROM workers WHERE id = ?', (payment['worker_id'],)).fetchone()
        if worker_user and worker_user['user_id']:
            send_worker_notification(worker_user['user_id'], 'Payment Confirmed',
                                     f'Payment of ₹{payment["amount"]} has been confirmed. Receipt: {payment["receipt_number"]}',
                                     url_for('main.payment_receipt', payment_id=payment_id))
        
        db.commit()
        return jsonify({'success': True})
    
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)})


@bp.route('/payment/<int:payment_id>/process', methods=['POST'])
@admin_required
def process_payment(payment_id):
    """Process a payment by recording method/details and marking completed."""
    db = get_db()
    payment = db.execute('SELECT * FROM payments WHERE id = ?', (payment_id,)).fetchone()
    if not payment:
        return jsonify({'success': False, 'error': 'Payment not found'})

    if payment['status'] == 'completed':
        return jsonify({'success': False, 'error': 'Payment already completed'})

    # Read form fields
    method = request.form.get('payment_method') or (request.json.get('payment_method') if request.is_json else None)
    upi_id = request.form.get('upi_id')
    bank_account = request.form.get('bank_account')
    bank_ifsc = request.form.get('ifsc')
    txn_ref = request.form.get('txn_ref')

    details = {}
    if method:
        details['method'] = method
    if upi_id:
        details['upi_id'] = upi_id
    if bank_account:
        details['bank_account'] = bank_account
    if bank_ifsc:
        details['ifsc'] = bank_ifsc
    if txn_ref:
        details['txn_ref'] = txn_ref

    try:
        # generate receipt if missing
        receipt = payment['receipt_number'] or generate_receipt_number()

        db.execute('''
            UPDATE payments
            SET status = 'completed',
                payment_method = ?,
                payment_details = ?,
                receipt_number = ?,
                confirmed_by = ?,
                confirmed_at = ?
            WHERE id = ?
        ''', (
            method,
            json.dumps(details),
            receipt,
            session.get('user_id'),
            datetime.now().isoformat(),
            payment_id
        ))

        # notify worker if linked
        worker_user = db.execute('SELECT user_id FROM workers WHERE id = ?', (payment['worker_id'],)).fetchone()
        if worker_user and worker_user['user_id']:
            send_worker_notification(worker_user['user_id'], 'Payment Processed',
                                     f'Payment of ₹{payment["amount"]} has been processed. Receipt: {receipt}',
                                     url_for('main.payment_receipt', payment_id=payment_id))

        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)})