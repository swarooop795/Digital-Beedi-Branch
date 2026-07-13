from app.models.database import get_db
from werkzeug.security import generate_password_hash, check_password_hash

class User:
    @staticmethod
    def create_user(username, password, role, customer_of=None):
        db = get_db()
        hashed_pw = generate_password_hash(password)
        db.execute('INSERT INTO users (username, password, role, customer_of) VALUES (?, ?, ?, ?)',
                   (username, hashed_pw, role, customer_of))
        db.commit()

    @staticmethod
    def create_admin_if_not_exists():
        db = get_db()
        # Create a default admin for development if it doesn't exist.
        # Updated default admin to username 'babu' with password 'babuadmin' per request.
        default_username = 'babu'
        default_password = 'babuadmin'
        user = db.execute('SELECT * FROM users WHERE username = ?', (default_username,)).fetchone()
        hashed_pw = generate_password_hash(default_password)
        if not user:
            db.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)',
                       (default_username, hashed_pw, 'admin'))
            db.commit()
        else:
            # Update password to the known default so the seeded credentials are usable.
            db.execute('UPDATE users SET password = ? WHERE id = ?', (hashed_pw, user['id']))
            db.commit()

    @staticmethod
    def get_by_username(username):
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        return user

    @staticmethod
    def check_password(user, password):
        return check_password_hash(user['password'], password)

    @staticmethod
    def get_by_id(user_id):
        db = get_db()
        return db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()

