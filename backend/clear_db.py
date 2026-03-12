import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), "raw_posts.db")
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("DELETE FROM raw_posts")
    conn.commit()
    conn.close()
    print("Database cleared successfully.")
else:
    print("Database does not exist yet.")
