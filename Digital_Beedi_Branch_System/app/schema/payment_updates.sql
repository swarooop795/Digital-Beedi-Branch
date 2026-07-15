
ALTER TABLE payments ADD COLUMN receipt_number TEXT;
ALTER TABLE payments ADD COLUMN payment_comment TEXT;
ALTER TABLE payments ADD COLUMN confirmed_by INTEGER REFERENCES users(id);
ALTER TABLE payments ADD COLUMN confirmed_at TEXT;
