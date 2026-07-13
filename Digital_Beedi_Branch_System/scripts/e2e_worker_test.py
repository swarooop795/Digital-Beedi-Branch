"""
End-to-end test for worker creation + worker login.
This script is intentionally small and uses the running Flask app started in-process.

Run from repository root:
  py scripts\e2e_worker_test.py

It will:
 - apply SQL migrations
 - start the Flask app in a subprocess
 - wait for /health
 - log in as admin (uses seeded admin credentials)
 - POST to /add-worker to create a worker with login credentials
 - attempt worker login and verify /worker-dashboard is reachable
 - print PASS/FAIL
"""
import os
import sys
import time
import subprocess
import requests

ROOT = os.path.dirname(os.path.dirname(__file__))

ADMIN_USERNAME = 'babuadmin'
ADMIN_PASSWORD = 'babu@8088'
WORKER_USERNAME = 'e2e_worker_user'
WORKER_PASSWORD = 'TestPass123!'


def apply_migrations():
    p = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'apply_migrations.py')], cwd=ROOT)
    if p.returncode != 0:
        raise SystemExit('apply_migrations failed')


def start_server():
    cmd = [sys.executable, '-u', '-c', "from app import app; app.run(debug=False)"]
    proc = subprocess.Popen(cmd, cwd=ROOT)
    return proc


def wait_health(timeout=30):
    url = 'http://127.0.0.1:5000/health'
    for _ in range(timeout):
        try:
            r = requests.get(url, timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def run_e2e():
    apply_migrations()
    proc = start_server()
    try:
        if not wait_health(30):
            raise SystemExit('Server did not become healthy in time')

        # Login as admin and create a worker
        s = requests.Session()
        login_url = 'http://127.0.0.1:5000/admin-login'
        resp = s.post(login_url, data={'username': ADMIN_USERNAME, 'password': ADMIN_PASSWORD}, allow_redirects=True)
        print('Admin login POST status:', resp.status_code)
        if resp.status_code not in (200, 302):
            print('Admin login failed, aborting')
            return

        add_worker_url = 'http://127.0.0.1:5000/add-worker'
        worker_data = {
            'name': 'E2E Test Worker',
            'contact': '9999999999',
            'address': '123 Test Lane',
            'aadhar_number': '111122223333',
            'bank_account': '123456789012',
            'contractor': 'Test Contractor',
            'username': WORKER_USERNAME,
            'password': WORKER_PASSWORD
        }
        r = s.post(add_worker_url, data=worker_data, allow_redirects=True)
        print('Add worker POST status:', r.status_code)
        # try worker login with new credentials
        s2 = requests.Session()
        wl = 'http://127.0.0.1:5000/worker-login'
        r2 = s2.post(wl, data={'username': WORKER_USERNAME, 'password': WORKER_PASSWORD}, allow_redirects=True)
        print('Worker login POST final status:', r2.status_code)

        # fetch dashboard
        dash = s2.get('http://127.0.0.1:5000/worker-dashboard')
        print('Worker dashboard GET status:', dash.status_code)

        if dash.status_code == 200:
            print('E2E WORKER TEST: PASS')
        else:
            print('E2E WORKER TEST: FAIL')

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == '__main__':
    run_e2e()
