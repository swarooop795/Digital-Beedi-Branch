from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify, send_file
from io import BytesIO
import pandas as pd
from app.models.database import get_db

bp = Blueprint('payment_report', __name__)

def get_date_range():
    to_date = request.args.get('to_date')
    if to_date:
        to_date = datetime.strptime(to_date, '%Y-%m-%d')
    else:
        to_date = datetime.now().date()

    from_date = request.args.get('from_date')
    if from_date:
        from_date = datetime.strptime(from_date, '%Y-%m-%d')
    else:
        from_date = to_date - timedelta(days=30)

    return from_date, to_date

@bp.route('/daily-report')
def daily_report():
    from_date, to_date = get_date_range()
    
    db = get_db()
    
    # Get all payments in date range
    payments = db.execute(
        '''SELECT p.*, w.name as worker_name 
           FROM payments p 
           JOIN workers w ON p.worker_id = w.id 
           WHERE date(payment_date) BETWEEN ? AND ?''',
        (from_date.strftime('%Y-%m-%d'), to_date.strftime('%Y-%m-%d'))
    ).fetchall()

    # Calculate summary stats
    total_amount = sum(p['amount'] for p in payments)
    days_diff = (to_date - from_date).days or 1

    pending_payments = db.execute(
        "SELECT COUNT(*) as count, SUM(amount) as total FROM payments WHERE status = 'pending'"
    ).fetchone()

    summary = {
        'total_amount': total_amount,
        'total_payments': len(payments),
        'worker_count': len(set(p['worker_id'] for p in payments)),
        'daily_average': total_amount / days_diff if payments else 0,
        'pending_amount': pending_payments['total'] or 0,
        'pending_count': pending_payments['count'] or 0
    }

    # Calculate daily summaries
    daily_summary = []
    current_date = from_date
    while current_date <= to_date:
        day_payments = [p for p in payments if p.payment_date.date() == current_date.date()]
        if day_payments:
            # Count payment methods
            methods = {}
            for payment in day_payments:
                methods[payment.payment_method] = methods.get(payment.payment_method, 0) + 1

            daily_summary.append({
                'date': current_date.strftime('%Y-%m-%d'),
                'payment_count': len(day_payments),
                'worker_count': len(set(p.worker_id for p in day_payments)),
                'total_amount': sum(p.amount for p in day_payments),
                'payment_methods': [
                    {'name': method, 'count': count}
                    for method, count in methods.items()
                ]
            })
        current_date += timedelta(days=1)

    return render_template('daily_payment_report.html',
                         summary=summary,
                         daily_summary=daily_summary,
                         from_date=from_date.strftime('%Y-%m-%d'),
                         to_date=to_date.strftime('%Y-%m-%d'))

@bp.route('/payment-report/day/<date>')
def day_details(date):
    try:
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        db = get_db()
        
        payments = db.execute(
            '''SELECT p.*, w.name as worker_name 
               FROM payments p 
               JOIN workers w ON p.worker_id = w.id 
               WHERE date(payment_date) = ?''',
            (date,)
        ).fetchall()

        return jsonify({
            'payments': [{
                'worker_name': p['worker_name'],
                'amount': "{:.2f}".format(p['amount']),
                'method': p['payment_method'],
                'time': datetime.strptime(p['payment_date'], '%Y-%m-%d %H:%M:%S').strftime('%I:%M %p'),
                'status': p['status']
            } for p in payments]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@bp.route('/payment-report/export')
def export_payment_report():
    from_date, to_date = get_date_range()
    
    # Query payments with worker information
    db = get_db()
    
    # Query payments with worker information
    payments = db.execute(
        '''SELECT p.*, w.name as worker_name 
           FROM payments p 
           JOIN workers w ON p.worker_id = w.id 
           WHERE date(payment_date) BETWEEN ? AND ?''',
        (from_date.strftime('%Y-%m-%d'), to_date.strftime('%Y-%m-%d'))
    ).fetchall()

    # Create DataFrame
    data = [{
        'Date': datetime.strptime(p['payment_date'], '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d'),
        'Time': datetime.strptime(p['payment_date'], '%Y-%m-%d %H:%M:%S').strftime('%I:%M %p'),
        'Worker ID': p['worker_id'],
        'Worker Name': p['worker_name'],
        'Amount': p['amount'],
        'Payment Method': p['payment_method'],
        'Status': p['status'],
    } for p in payments]

    df = pd.DataFrame(data)
    
    # Create Excel file
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Payment Report', index=False)
        workbook = writer.book
        worksheet = writer.sheets['Payment Report']
        
        # Add some formatting
        money_format = workbook.add_format({'num_format': '₹#,##0.00'})
        worksheet.set_column('E:E', 12, money_format)  # Format amount column
        worksheet.set_column('A:D', 15)  # Set width for other columns
        worksheet.set_column('F:G', 15)  # Set width for other columns
        
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'payment_report_{from_date.strftime("%Y%m%d")}-{to_date.strftime("%Y%m%d")}.xlsx'
    )