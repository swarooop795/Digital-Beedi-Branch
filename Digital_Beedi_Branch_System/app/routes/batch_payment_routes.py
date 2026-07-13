from flask import render_template, session, redirect, url_for, request, jsonify, current_app
from app.models.database import get_db
from datetime import datetime
import json

# reuse main blueprint and helpers
from app.routes.main_routes import bp as main_bp, admin_required, generate_receipt_number
from app.utils.notifications import send_worker_notification
import razorpay

bp = main_bp


@bp.route('/wages/batch')
@admin_required
def batch_payment():
    db = get_db()
    unpaid_entries = db.execute('''
        SELECT b.*, w.name as worker_name
        FROM beedi_entries b
        JOIN workers w ON b.worker_id = w.id
        WHERE b.is_paid = 0 AND b.admin_id = ?
        ORDER BY b.entry_time DESC
    ''', (session['user_id'],)).fetchall()
    
    return render_template('batch_payment.html', unpaid_entries=unpaid_entries)

@bp.route('/wages/batch-pay', methods=['POST'])
@admin_required
def process_batch_payment():
    if not request.is_json:
        return jsonify({'success': False, 'error': 'Invalid request format'})
    
    data = request.get_json()
    entries = data.get('entries', [])
    payment_method = data.get('payment_method')
    payment_details = data.get('payment_details', {})
    
    if not entries or not payment_method:
        return jsonify({'success': False, 'error': 'Missing required data'})
    
    db = get_db()
    try:
        processed = 0
        total_amount = 0
        
        for entry_id in entries:
            # Get entry details
            entry = db.execute('''
                SELECT b.*, w.id as worker_id, w.name as worker_name, w.contact as worker_contact
                FROM beedi_entries b 
                JOIN workers w ON b.worker_id = w.id 
                WHERE b.id = ?
            ''', (entry_id,)).fetchone()
            
            if not entry or entry['is_paid']:
                continue
                
            # Calculate payment amount
            payment_amount = entry['price'] * entry['quantity']
            total_amount += payment_amount
            
            # Generate receipt number
            receipt_number = generate_receipt_number()
            
            # Create payment record
            payment_id = db.execute('''
                INSERT INTO payments (
                    worker_id, amount, payment_method, payment_details,
                    receipt_number, status, payment_date,
                    created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                entry['worker_id'],
                payment_amount,
                payment_method,
                json.dumps(payment_details),
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
                                         f'Payment of ₹{payment_amount} processed via {payment_method}. Receipt: {receipt_number}',
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
                                "address": payment_details.get('upi_id', '')
                            }
                        }
                    elif payment_method == 'Bank Transfer':
                        fund_account_data = {
                            "contact_id": contact['id'],
                            "account_type": "bank_account",
                            "bank_account": {
                                "name": entry['worker_name'],
                                "ifsc": payment_details.get('ifsc_code', ''),
                                "account_number": payment_details.get('account_number', '')
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
            
            processed += 1
        
        db.commit()
        return jsonify({
            'success': True,
            'processed': processed,
            'total_amount': total_amount
        })
        
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)})