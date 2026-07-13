from flask import Blueprint, request, jsonify
from app.models.attendance import Attendance

bp = Blueprint('attendance', __name__, url_prefix='/api/attendance')

@bp.route('/mark', methods=['POST'])
def mark_attendance():
    data = request.get_json()
    try:
        attendance = Attendance.mark_attendance(
            worker_id=data['worker_id'],
            status=data.get('status', 'present'),
            work_hours=data.get('work_hours', 8)
        )
        return jsonify({'message': 'Attendance marked successfully', 'attendance': attendance.to_dict()}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@bp.route('/<worker_id>', methods=['GET'])
def get_worker_attendance(worker_id):
    try:
        attendance_records = Attendance.get_worker_attendance(worker_id)
        return jsonify({'attendance_records': attendance_records}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400