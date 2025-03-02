import sqlite3
import os

def migrate_database():
    """Add the objections column to the existing calls table if it doesn't exist"""
    
    # Check if database exists
    if not os.path.exists('sales_calls.db'):
        print("Database does not exist. No migration needed.")
        return False
    
    conn = sqlite3.connect('sales_calls.db')
    cursor = conn.cursor()
    
    # Check if objections column already exists
    cursor.execute("PRAGMA table_info(calls)")
    columns = cursor.fetchall()
    column_names = [column[1] for column in columns]
    
    if 'objections' not in column_names:
        try:
            cursor.execute("ALTER TABLE calls ADD COLUMN objections TEXT")
            conn.commit()
            print("Successfully added 'objections' column to the calls table.")
        except sqlite3.Error as e:
            print(f"Error adding column: {e}")
            conn.close()
            return False
    else:
        print("Column 'objections' already exists. No migration needed.")
    
    conn.close()
    return True

if __name__ == "__main__":
    migrate_database()
