import sqlite3
from flask import g
import os

DATABASE = os.path.join(os.path.dirname(__file__), '../../beedi_workers.db')

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with sqlite3.connect(DATABASE) as db:
        cursor = db.cursor()
        # Users table (admin, customer)
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'customer')),
            customer_of INTEGER,
            FOREIGN KEY(customer_of) REFERENCES users(id)
        )''')
        # Workers table
        cursor.execute('''CREATE TABLE IF NOT EXISTS workers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact TEXT,
            address TEXT,
            aadhar_number TEXT,
            admin_id INTEGER,
            user_id INTEGER,
            bank_account TEXT,
            ifsc_code TEXT,
            upi_id TEXT,
            contractor TEXT,
            rate REAL DEFAULT 1.5,
            FOREIGN KEY(admin_id) REFERENCES users(id)
        )''')
        # Beedi entries table
        cursor.execute('''CREATE TABLE IF NOT EXISTS beedi_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id INTEGER,
            price REAL,
            quantity INTEGER,
            entry_time TEXT,
            admin_id INTEGER,
            is_paid INTEGER DEFAULT 0,
            payment_method TEXT,
            payment_id INTEGER,
            payment_details TEXT,
            payment_comment TEXT,
            FOREIGN KEY(worker_id) REFERENCES workers(id),
            FOREIGN KEY(admin_id) REFERENCES users(id)
        )''')
        # Notifications table
        cursor.execute('''CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message TEXT,
            is_read INTEGER DEFAULT 0,
            created_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )''')
        # Todo table
        cursor.execute('''CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            task TEXT NOT NULL,
            is_done INTEGER DEFAULT 0,
            created_at TEXT,
            FOREIGN KEY(admin_id) REFERENCES users(id)
        )''')
        # Attendance table
        cursor.execute('''CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id INTEGER,
            date TEXT,
            status TEXT,
            admin_id INTEGER,
            FOREIGN KEY(worker_id) REFERENCES workers(id),
            FOREIGN KEY(admin_id) REFERENCES users(id)
        )''')
        # Payments table (used by reporting and payment flows)
        cursor.execute('''CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            payment_method TEXT,
            payment_details TEXT,
            payment_comment TEXT,
            receipt_number TEXT UNIQUE,
            status TEXT DEFAULT 'pending',
            payment_date TEXT,
            created_by INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(worker_id) REFERENCES workers(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        )''')

        # Payment schedules for future/recurring payments
        cursor.execute('''CREATE TABLE IF NOT EXISTS payment_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id INTEGER NOT NULL,
            admin_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            scheduled_date TEXT NOT NULL,
            payment_method TEXT,
            notes TEXT,
            send_reminder INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(worker_id) REFERENCES workers(id),
            FOREIGN KEY(admin_id) REFERENCES users(id)
        )''')

        # Payment reconciliation / tracking tables
        cursor.execute('''CREATE TABLE IF NOT EXISTS payment_reconciliation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id INTEGER NOT NULL,
            admin_id INTEGER NOT NULL,
            expected_amount REAL,
            actual_amount REAL,
            status TEXT DEFAULT 'pending',
            date TEXT,
            notes TEXT,
            verified_at TEXT,
            FOREIGN KEY(worker_id) REFERENCES workers(id),
            FOREIGN KEY(admin_id) REFERENCES users(id)
        )''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS payment_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reconciliation_id INTEGER NOT NULL,
            amount REAL,
            payment_method TEXT,
            status TEXT,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(reconciliation_id) REFERENCES payment_reconciliation(id)
        )''')
        # Work log: admin logs daily collections which become a payment queue item
        cursor.execute('''CREATE TABLE IF NOT EXISTS work_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id INTEGER NOT NULL,
            quantity_collected INTEGER NOT NULL,
            rate REAL NOT NULL,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'processing',
            payment_id INTEGER,
            processed_by_admin_id INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(worker_id) REFERENCES workers(id),
            FOREIGN KEY(payment_id) REFERENCES payments(id),
            FOREIGN KEY(processed_by_admin_id) REFERENCES users(id)
        )''')
        db.commit()
        # Ensure beedi_entries has payment_id / payment_details / payment_comment columns for linking payments
        try:
            cols = [r[1] for r in db.execute("PRAGMA table_info(beedi_entries)").fetchall()]
            to_add = []
            if 'payment_id' not in cols:
                to_add.append(('payment_id', 'INTEGER'))
            if 'payment_details' not in cols:
                to_add.append(('payment_details', 'TEXT'))
            if 'payment_comment' not in cols:
                to_add.append(('payment_comment', 'TEXT'))
            for col_name, col_type in to_add:
                try:
                    db.execute(f'ALTER TABLE beedi_entries ADD COLUMN {col_name} {col_type}')
                except Exception:
                    # Non-fatal: if ALTER fails (old SQLite versions or locked DB), continue
                    pass
            if to_add:
                db.commit()
        except Exception:
            pass
        # Ensure workers.user_id column exists for linking a users row to a worker profile
        try:
            cols = [r[1] for r in db.execute("PRAGMA table_info(workers)").fetchall()]
            to_add = []
            if 'user_id' not in cols:
                to_add.append(('user_id', 'INTEGER'))
            if 'bank_account' not in cols:
                to_add.append(('bank_account', 'TEXT'))
            if 'ifsc_code' not in cols:
                to_add.append(('ifsc_code', 'TEXT'))
            if 'upi_id' not in cols:
                to_add.append(('upi_id', 'TEXT'))
            if 'contractor' not in cols:
                to_add.append(('contractor', 'TEXT'))
            if 'rate' not in cols:
                to_add.append(('rate', 'REAL DEFAULT 1.5'))
            for col_name, col_type in to_add:
                try:
                    db.execute(f'ALTER TABLE workers ADD COLUMN {col_name} {col_type}')
                except Exception:
                    pass
            if to_add:
                db.commit()
        except Exception:
            # Non-fatal: if ALTER fails (old DB quirks), continue — admin can link users manually
            pass
