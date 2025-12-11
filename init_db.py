import sqlite3
import os

DB_PATH = os.path.join("instance", "database.db")

def init_db():
    # Make sure instance folder exists
    os.makedirs("instance", exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # ----- USERS TABLE -----
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT,         -- 'student' or 'teacher'
            name TEXT          -- optional display name
        )
    """)

    # ----- PRACTICE LOGS TABLE -----
    c.execute("""
        CREATE TABLE IF NOT EXISTS practice_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT,
            hours REAL,
            notes TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # ----- NOTIFICATIONS TABLE -----
    c.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER,
            title TEXT,
            message TEXT,
            timestamp TEXT,
            file_path TEXT,
            FOREIGN KEY (teacher_id) REFERENCES users(id)
        )
    """)

    # ----- PUBLIC MUSIC LIBRARY -----
    c.execute("""
        CREATE TABLE IF NOT EXISTS public_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER,
            file_name TEXT,
            file_path TEXT,
            description TEXT,
            timestamp TEXT,
            FOREIGN KEY (teacher_id) REFERENCES users(id)
        )
    """)

    # ----- PRIVATE MUSIC LIBRARY -----
    c.execute("""
        CREATE TABLE IF NOT EXISTS private_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            file_name TEXT,
            file_path TEXT,
            description TEXT,
            timestamp TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # ----- SMART SUGGESTIONS -----
    c.execute("""
        CREATE TABLE IF NOT EXISTS suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            suggestion TEXT,
            timestamp TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()

    # ----- INSERT DEFAULT USERS -----
    print("Inserting default accounts...")

    # 50 STUDENTS: usernames 10001–10050
    for i in range(10001, 10051):
        c.execute("""
            INSERT OR IGNORE INTO users (username, password, role, name)
            VALUES (?, ?, 'student', ?)
        """, (str(i), str(i), f"Student {i}"))

    # 10 TEACHERS: usernames 70001–70010
    for i in range(70001, 70011):
        c.execute("""
            INSERT OR IGNORE INTO users (username, password, role, name)
            VALUES (?, ?, 'teacher', ?)
        """, (str(i), str(i), f"Teacher {i}"))

    conn.commit()
    conn.close()
    print("Database initialized successfully!")


if __name__ == "__main__":
    init_db()