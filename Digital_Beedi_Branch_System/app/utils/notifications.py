from app.models.database import get_db
from datetime import datetime


def send_worker_notification(user_id: int, title: str, body: str, url: str = None):
    """
    Insert a notification row for the given user_id.

    Parameters:
    - user_id: ID of the user to notify (can be None for system notices)
    - title: short title for the notification
    - body: full message/body shown in the list
    - url: optional relative URL (e.g., url_for('worker_routes.worker_dashboard')) that the
           notification links to when shown in the UI

    Returns True on success, False on failure.
    """
    db = get_db()
    created_at = datetime.now().isoformat(sep=' ', timespec='seconds')
    try:
        db.execute('INSERT INTO notifications (user_id, title, message, url, created_at) VALUES (?, ?, ?, ?, ?)',
                   (user_id, title, body, url, created_at))
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False
