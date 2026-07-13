-- Migration: remove two_factor_secret column from users table (SQLite)
-- SQLite doesn't support DROP COLUMN directly on older versions; recreate the table without the column.
PRAGMA foreign_keys=off;
BEGIN TRANSACTION;

-- Create a new table without the two_factor_secret column
CREATE TABLE IF NOT EXISTS users_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'customer')),
    customer_of INTEGER,
    FOREIGN KEY(customer_of) REFERENCES users(id)
);

-- Copy data across (exclude two_factor_secret)
INSERT INTO users_new (id, username, password, role, customer_of)
SELECT id, username, password, role, customer_of FROM users;

-- Drop old table and rename new
DROP TABLE users;
ALTER TABLE users_new RENAME TO users;

COMMIT;
PRAGMA foreign_keys=on;
