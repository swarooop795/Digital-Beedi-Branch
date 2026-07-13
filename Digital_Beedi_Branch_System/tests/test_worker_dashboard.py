import pytest
from app import app as flask_app
from app.models.database import get_db

@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as client:
        yield client


def test_worker_dashboard_renders(client):
    # Create a temporary worker in DB
    with flask_app.app_context():
        db = get_db()
        cur = db.execute("INSERT INTO workers (name, contact, address, admin_id) VALUES (?, ?, ?, ?)",
                         ("TestWorker", "0000000000", "Test Address", 1))
        worker_id = cur.lastrowid
        db.commit()

    # Set session as worker
    with client.session_transaction() as sess:
        sess['user_id'] = 999999
        sess['role'] = 'worker'
        sess['worker_id'] = worker_id

    resp = client.get('/worker-dashboard')
    assert resp.status_code == 200
    data = resp.get_data(as_text=True)
    assert 'Worker Dashboard' in data

    # Cleanup: remove the test worker
    with flask_app.app_context():
        db = get_db()
        db.execute('DELETE FROM workers WHERE id = ?', (worker_id,))
        db.commit()
