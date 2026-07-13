from app.models.database import DATABASE
import sqlite3

def add_payment_schedule_table():
    """
    Creates the payment_schedules table
    """
    try:
        with sqlite3.connect(DATABASE) as db:
            cursor = db.cursor()
            
            cursor.execute('''CREATE TABLE IF NOT EXISTS payment_schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worker_id INTEGER NOT NULL,
                admin_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                scheduled_date TEXT NOT NULL,
                payment_method TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                notes TEXT,
                send_reminder INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(worker_id) REFERENCES workers(id),
                FOREIGN KEY(admin_id) REFERENCES users(id)
            )''')
            
            # Index for faster lookups
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_payment_schedules_date 
                            ON payment_schedules(scheduled_date)''')
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_payment_schedules_status 
                            ON payment_schedules(status)''')
            
            db.commit()
            print("Successfully created payment_schedules table")
                
    except sqlite3.Error as e:
        print(f"Error creating payment_schedules table: {e}")

if __name__ == '__main__':
    add_payment_schedule_table()