"""
Create or update the default admin user to username 'babu' with password 'babuadmin'.
Run from project root:
  python scripts\set_admin.py
"""
import sqlite3
from werkzeug.security import generate_password_hash
import os

DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'beedi_workers.db')

def main():
    username = 'babu'
    password = 'babuadmin'
    hashed = generate_password_hash(password)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('SELECT id FROM users WHERE username = ?', (username,))
    row = cur.fetchone()
    if row:
        cur.execute('UPDATE users SET password = ? WHERE id = ?', (hashed, row['id']))
        print(f"Updated password for existing user '{username}'")
    else:
        cur.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)', (username, hashed, 'admin'))
        print(f"Created admin user '{username}'")
    conn.commit()
    conn.close()

if __name__ == '__main__':
    main()
