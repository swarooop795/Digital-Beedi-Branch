from app.models.database import DATABASE
import sqlite3

def add_payment_details_column():
    """
    Adds payment_details column to beedi_entries table if it doesn't exist
    """
    try:
        with sqlite3.connect(DATABASE) as db:
            cursor = db.cursor()
            # Check if column exists
            cursor.execute("PRAGMA table_info(beedi_entries)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'payment_details' not in columns:
                cursor.execute('''ALTER TABLE beedi_entries 
                                ADD COLUMN payment_details TEXT''')
                db.commit()
                print("Successfully added payment_details column")
            else:
                print("payment_details column already exists")
                
    except sqlite3.Error as e:
        print(f"Error adding payment_details column: {e}")
        
if __name__ == '__main__':
    add_payment_details_column()