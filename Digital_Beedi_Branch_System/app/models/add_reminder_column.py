from app.models.database import DATABASE
import sqlite3

def add_reminder_column():
    """
    Adds is_reminder column to notifications table if it doesn't exist
    """
    try:
        with sqlite3.connect(DATABASE) as db:
            cursor = db.cursor()
            # Check if column exists
            cursor.execute("PRAGMA table_info(notifications)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'is_reminder' not in columns:
                cursor.execute('''ALTER TABLE notifications 
                                ADD COLUMN is_reminder INTEGER DEFAULT 0''')
                db.commit()
                print("Successfully added is_reminder column")
            else:
                print("is_reminder column already exists")
                
    except sqlite3.Error as e:
        print(f"Error adding is_reminder column: {e}")

if __name__ == '__main__':
    add_reminder_column()