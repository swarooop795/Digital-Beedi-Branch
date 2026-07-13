from app.models.database import DATABASE
import sqlite3

def add_reconciliation_table():
    """
    Creates the payment_reconciliation table
    """
    try:
        with sqlite3.connect(DATABASE) as db:
            cursor = db.cursor()
            
            cursor.execute('''CREATE TABLE IF NOT EXISTS payment_reconciliation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id INTEGER NOT NULL,
                admin_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                expected_amount REAL NOT NULL,
                actual_amount REAL DEFAULT 0,
                status TEXT DEFAULT 'pending',
                notes TEXT,
                verified_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(worker_id) REFERENCES workers(id),
                FOREIGN KEY(admin_id) REFERENCES users(id)
            )''')
            
            # Indices for faster lookups
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_reconciliation_date 
                            ON payment_reconciliation(date)''')
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_reconciliation_status 
                            ON payment_reconciliation(status)''')
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_reconciliation_worker 
                            ON payment_reconciliation(worker_id)''')
            
            db.commit()
            print("Successfully created payment_reconciliation table")
                
    except sqlite3.Error as e:
        print(f"Error creating payment_reconciliation table: {e}")

def add_payment_tracking_table():
    """
    Creates the payment_tracking table for detailed transaction records
    """
    try:
        with sqlite3.connect(DATABASE) as db:
            cursor = db.cursor()
            
            cursor.execute('''CREATE TABLE IF NOT EXISTS payment_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reconciliation_id INTEGER,
                amount REAL NOT NULL,
                payment_method TEXT,
                transaction_id TEXT,
                status TEXT DEFAULT 'pending',
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(reconciliation_id) REFERENCES payment_reconciliation(id)
            )''')
            
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_tracking_reconciliation 
                            ON payment_tracking(reconciliation_id)''')
            
            db.commit()
            print("Successfully created payment_tracking table")
                
    except sqlite3.Error as e:
        print(f"Error creating payment_tracking table: {e}")

if __name__ == '__main__':
    add_reconciliation_table()
    add_payment_tracking_table()