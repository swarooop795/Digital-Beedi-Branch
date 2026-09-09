        cursor.execute('''CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL UNIQUE,
            quantity REAL NOT NULL DEFAULT 0,
            type_of_item TEXT NOT NULL,
            last_updated TEXT NOT NULL
        )''')

        # Ensure required columns exist in existing databases
        def ensure_column(table, column, column_type):
            columns = [row[1] for row in db.execute(
                f"PRAGMA table_info({table})"
            ).fetchall()]

            if column not in columns:
                try:
                    db.execute(
                        f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"
                    )
                except sqlite3.OperationalError:
                    pass

        ensure_column('attendance', 'work_hours', 'REAL DEFAULT 8')
        ensure_column('attendance', 'timestamp', 'TEXT')

        ensure_column('notifications', 'title', 'TEXT')
        ensure_column('notifications', 'url', 'TEXT')

        ensure_column('payments', 'confirmed_by', 'INTEGER')
        ensure_column('payments', 'confirmed_at', 'TEXT')

        db.commit()

        # Ensure beedi_entries has payment_id / payment_details / payment_comment
        # columns for linking payments
        try:
            cols = [r[1] for r in db.execute(
                "PRAGMA table_info(beedi_entries)"
            ).fetchall()]

            to_add = []

            if 'payment_id' not in cols:
                to_add.append(('payment_id', 'INTEGER'))

            if 'payment_details' not in cols:
                to_add.append(('payment_details', 'TEXT'))

            if 'payment_comment' not in cols:
                to_add.append(('payment_comment', 'TEXT'))

            for col_name, col_type in to_add:
                try:
                    db.execute(
                        f'ALTER TABLE beedi_entries ADD COLUMN {col_name} {col_type}'
                    )
                except Exception:
                    # Non-fatal: if ALTER fails (old SQLite versions or locked DB),
                    # continue
                    pass

            if to_add:
                db.commit()

        except Exception:
            pass

        # Ensure workers.user_id column exists for linking a users row to a worker profile
        try:
            cols = [r[1] for r in db.execute(
                "PRAGMA table_info(workers)"
            ).fetchall()]

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
                    db.execute(
                        f'ALTER TABLE workers ADD COLUMN {col_name} {col_type}'
                    )
                except Exception:
                    pass

            if to_add:
                db.commit()

        except Exception:
            # Non-fatal: if ALTER fails (old DB quirks), continue —
            # admin can link users manually
            pass
