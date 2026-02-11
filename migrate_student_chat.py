import sqlite3

def migrate():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    try:
        # Check if student_id column exists
        cursor.execute("PRAGMA table_info(chat_conversation)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if 'student_id' not in columns:
            print("Adding student_id column to chat_conversation...")
            cursor.execute("ALTER TABLE chat_conversation ADD COLUMN student_id INTEGER REFERENCES student(id)")
            
        print("Migration completed successfully.")
        conn.commit()
    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
