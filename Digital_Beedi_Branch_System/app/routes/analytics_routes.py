from flask import Blueprint, jsonify

from datetime import datetime, timedelta
from app.models.database import get_db

bp = Blueprint('analytics', __name__, url_prefix='/api/analytics')

@bp.route('/worker-stats', methods=['GET'])
def worker_stats():
    try:
        db = get_db()
        total_workers = db.execute('SELECT COUNT(*) FROM workers').fetchone()[0]
        date_30_days_ago = (datetime.now() - timedelta(days=30)).date()
        active_workers = db.execute('SELECT DISTINCT worker_id FROM beedi_entries WHERE DATE(entry_time) >= ?', (date_30_days_ago,)).fetchall()
        stats = {
            'total_workers': total_workers,
            'active_workers': len(active_workers)
        }
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@bp.route('/inventory-stats', methods=['GET'])
def inventory_stats():
    try:
        db = get_db()
        raw_materials = db.execute('SELECT * FROM inventory WHERE type_of_item = ?', ('raw_material',)).fetchall()
        finished_goods = db.execute('SELECT * FROM inventory WHERE type_of_item = ?', ('finished_goods',)).fetchall()
        stats = {
            'raw_materials_count': len(raw_materials),
            'finished_goods_count': len(finished_goods),
            'raw_materials': [dict(row) for row in raw_materials],
            'finished_goods': [dict(row) for row in finished_goods]
        }
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400