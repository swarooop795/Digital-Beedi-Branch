"""
Smoke test for local development.

This script:
 - applies SQL migrations under app/schema/
 - starts the Flask app in a subprocess (no reloader)
 - waits for /health to become available
 - performs admin login (username/password) and verifies admin dashboard
 - stops the server

Run from repository root:
  py scripts\smoke_test.py
"""
import subprocess
import sys
import os
import time
import sqlite3
import requests

ROOT = os.path.dirname(os.path.dirname(__file__))
DB = os.path.join(ROOT, 'beedi_workers.db')

def apply_migrations():
    p = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'apply_migrations.py')], cwd=ROOT)
    if p.returncode != 0:
        raise SystemExit('apply_migrations failed')

def start_server():
    # Start server without reloader to keep it in a single process
    cmd = [sys.executable, '-u', '-c', "from app import app; app.run(debug=False)"]
    proc = subprocess.Popen(cmd, cwd=ROOT)
    return proc

def wait_health(timeout=30):
    url = 'http://127.0.0.1:5000/health'
    for i in range(timeout):
        try:
            r = requests.get(url, timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def run_smoke():
    apply_migrations()
    proc = start_server()
    try:
        if not wait_health(30):
            raise SystemExit('Server did not become healthy in time')

        s = requests.Session()
        login_url = 'http://127.0.0.1:5000/admin-login'
        resp = s.post(login_url, data={'username':'babuadmin','password':'babu@8088'}, allow_redirects=True)
        print('Login POST status:', resp.status_code)

        # Check admin dashboard (login should land here directly for admin)
        r = s.get('http://127.0.0.1:5000/admin-dashboard')
        print('Admin dashboard status:', r.status_code)
        if r.status_code == 200:
            print('SMOKE TEST: PASS')
        else:
            print('SMOKE TEST: FAIL')

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

if __name__ == '__main__':
    run_smoke()
