-- Migration: Create payments table used by routes and reporting
-- Save as a new migration file and run it against the SQLite DB or add to init_db() if you want it created at startup.

CREATE TABLE IF NOT EXISTS payments (
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
);

-- Optional indexes for reporting
CREATE INDEX IF NOT EXISTS idx_payments_worker_id ON payments(worker_id);
CREATE INDEX IF NOT EXISTS idx_payments_payment_date ON payments(payment_date);
