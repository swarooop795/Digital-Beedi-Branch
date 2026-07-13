"""
Run all .sql migration files found in app/schema/ against the SQLite DB.
This script is idempotent for files that use IF NOT EXISTS and is intended for
local development or CI use before starting the app.

Usage (PowerShell):
  py scripts\apply_migrations.py
"""
import sqlite3
import os

ROOT = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(ROOT, 'beedi_workers.db')
SCHEMA_DIR = os.path.join(ROOT, 'app', 'schema')

def apply_sql_file(cursor, path):
    print(f"Applying {path}")
    with open(path, 'r', encoding='utf-8') as f:
        sql = f.read()
    try:
        cursor.executescript(sql)
    except Exception as e:
        # Log and continue — useful when ALTERs have already been applied on the DB
        print(f"Warning applying {path}: {e}")

def main():
    files = sorted([f for f in os.listdir(SCHEMA_DIR) if f.endswith('.sql')])
    if not files:
        print('No migration files found in', SCHEMA_DIR)
        return

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        for fname in files:
            apply_sql_file(cur, os.path.join(SCHEMA_DIR, fname))
        conn.commit()
        print('Migrations applied successfully')
    finally:
        conn.close()

if __name__ == '__main__':
    main()
