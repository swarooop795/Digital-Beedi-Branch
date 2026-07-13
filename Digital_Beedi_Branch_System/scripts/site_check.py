"""
Site-wide quick checker.
- Applies migrations
- Starts the Flask app in a subprocess
- Waits until /health responds
- Requests a list of common pages and reports status codes and first 200 chars of body when errors appear

Run from repo root:
  py scripts\site_check.py
"""
import os
import sys
import time
import subprocess
import requests

ROOT = os.path.dirname(os.path.dirname(__file__))

PAGES = [
    '/',
    '/health',
    '/admin-login',
    '/worker-login',
    '/admin-dashboard',
    '/workers',
    '/add-worker',
    '/worker-dashboard',
    '/payment_dashboard',
    '/payment_report',
    '/payment_reconciliation',
    '/payment_schedule',
    '/wages',
    '/register',
]


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


def run_check():
    apply_migrations()
    proc = start_server()
    try:
        if not wait_health(30):
            raise SystemExit('Server did not become healthy in time')

        s = requests.Session()
        base = 'http://127.0.0.1:5000'
        any_error = False
        for p in PAGES:
            try:
                url = base + p
                r = s.get(url, allow_redirects=True, timeout=5)
                sc = r.status_code
                print(f'{p:30} -> {sc}')
                if sc >= 500:
                    any_error = True
                    print('--- body snippet ---')
                    print(r.text[:1000])
                    print('--- end body ---')
            except Exception as e:
                any_error = True
                print(f'{p:30} -> ERROR: {e}')
        if any_error:
            print('SITE CHECK: ERRORS FOUND')
        else:
            print('SITE CHECK: OK')
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

if __name__ == '__main__':
    run_check()
