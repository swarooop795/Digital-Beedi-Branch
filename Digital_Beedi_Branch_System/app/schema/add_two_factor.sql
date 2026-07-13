-- Add two_factor_secret column to users table for TOTP 2FA
ALTER TABLE users ADD COLUMN two_factor_secret TEXT;
