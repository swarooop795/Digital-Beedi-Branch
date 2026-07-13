from datetime import datetime


class Attendance:
    def __init__(self, worker_id, date, status, work_hours=0):
        self.worker_id = worker_id
        self.date = date
        self.status = status
        self.work_hours = work_hours
        self.timestamp = datetime.now()

    def to_dict(self):
        return {
            'worker_id': self.worker_id,
            'date': self.date,
            'status': self.status,
            'work_hours': self.work_hours,
            'timestamp': self.timestamp
        }


    @staticmethod
    def mark_attendance(worker_id, status='present', work_hours=8):
        from app.models.database import get_db
        db = get_db()
        date = datetime.now().date()
        timestamp = datetime.now()
        db.execute(
            'INSERT INTO attendance (worker_id, date, status, work_hours, timestamp) VALUES (?, ?, ?, ?, ?)',
            (worker_id, date, status, work_hours, timestamp)
        )
        db.commit()
        return Attendance(worker_id, date, status, work_hours)


    @staticmethod
    def get_worker_attendance(worker_id):
        from app.models.database import get_db
        db = get_db()
        rows = db.execute('SELECT * FROM attendance WHERE worker_id = ?', (worker_id,)).fetchall()
        return [dict(row) for row in rows]