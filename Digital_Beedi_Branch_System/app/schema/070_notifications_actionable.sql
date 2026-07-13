-- Migration: add title and url columns to notifications for actionable notifications
ALTER TABLE notifications ADD COLUMN title TEXT;
ALTER TABLE notifications ADD COLUMN url TEXT;
