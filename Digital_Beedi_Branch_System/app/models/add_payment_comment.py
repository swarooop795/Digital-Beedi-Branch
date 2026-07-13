from app.models.database import DATABASE
import sqlite3

def add_payment_comment_column():
    """
    Adds payment_comment column to beedi_entries table if it doesn't exist
    """
    try:
        with sqlite3.connect(DATABASE) as db:
            cursor = db.cursor()
            # Check if column exists
            cursor.execute("PRAGMA table_info(beedi_entries)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'payment_comment' not in columns:
                cursor.execute('''ALTER TABLE beedi_entries 
                                ADD COLUMN payment_comment TEXT''')
                db.commit()
                print("Successfully added payment_comment column")
            else:
                print("payment_comment column already exists")
                
    except sqlite3.Error as e:
        print(f"Error adding payment_comment column: {e}")

if __name__ == '__main__':
    add_payment_comment_column()