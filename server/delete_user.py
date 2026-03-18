import sqlite3
import sys
from pathlib import Path

DATABASE_PATH = Path(__file__).parent / "messenger.db"

def delete_user(username: str):
    if not DATABASE_PATH.exists():
        print(f"Error: Database not found at {DATABASE_PATH}")
        return

    conn = sqlite3.connect(str(DATABASE_PATH))
    try:
        # 1. Delete the user from the contact list
        cursor = conn.execute("DELETE FROM users WHERE username = ?", (username,))
        
        if cursor.rowcount > 0:
            print(f"✅ Successfully deleted '{username}' from the contacts list.")
            conn.commit()
        else:
            print(f"⚠️ User '{username}' was not found in the database.")
            
    except Exception as e:
        print(f"❌ Error deleting user: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python delete_user.py <username>")
        print("Example: python delete_user.py nurses")
        sys.exit(1)
        
    target_user = sys.argv[1]
    delete_user(target_user)
