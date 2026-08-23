import sqlite3
import hashlib
from datetime import datetime, date
import hmac
from app.config import DB_PATH

def hash_password(password: str) -> str:
    """Standard secure pbkdf2_hmac password hasher (Python built-in)."""
    return hashlib.pbkdf2_hmac(
        'sha256', 
        password.encode('utf-8'), 
        b'sports_erp_salt_2026', 
        100000
    ).hex()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return hmac.compare_digest(hash_password(plain_password), hashed_password)

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def reset_db_for_tests():
    if "test" not in DB_PATH.lower():
        raise RuntimeError(
            f"Safety Guard: reset_db_for_tests() cannot be executed on production database '{DB_PATH}'. "
            "It is strictly restricted to test databases containing 'test' in their filename."
        )
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS attendance")
    cursor.execute("DROP TABLE IF EXISTS bookings")
    cursor.execute("DROP TABLE IF EXISTS facilities")
    cursor.execute("DROP TABLE IF EXISTS sports")
    cursor.execute("DROP TABLE IF EXISTS users")
    conn.commit()
    conn.close()
    init_db()

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        hashed_password TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'student',
        is_blocked INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Sports Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        category TEXT NOT NULL,
        description TEXT,
        min_players INTEGER DEFAULT 1,
        max_players INTEGER DEFAULT 22,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Facilities Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS facilities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        sport_id INTEGER NOT NULL,
        location TEXT NOT NULL,
        capacity INTEGER DEFAULT 10,
        is_available INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sport_id) REFERENCES sports(id) ON DELETE CASCADE
    )
    """)

    # Bookings Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        facility_id INTEGER NOT NULL,
        sport_id INTEGER NOT NULL,
        booking_date TEXT NOT NULL,
        time_slot TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'confirmed',
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (facility_id) REFERENCES facilities(id) ON DELETE CASCADE,
        FOREIGN KEY (sport_id) REFERENCES sports(id) ON DELETE CASCADE
    )
    """)

    # Attendance Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        check_in_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT NOT NULL DEFAULT 'present',
        marked_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (marked_by) REFERENCES users(id)
    )
    """)

    conn.commit()
    seed_data(conn)
    conn.close()

def seed_data(conn):
    cursor = conn.cursor()

    # Check if users already seeded
    cursor.execute("SELECT COUNT(*) as count FROM users")
    if cursor.fetchone()["count"] == 0:
        users = [
            ("Admin User", "admin@sports.edu", hash_password("admin123"), "admin", 0),
            ("Rahul Sharma", "student@sports.edu", hash_password("student123"), "student", 0),
            ("Priya Patel", "priya@sports.edu", hash_password("priya123"), "student", 0),
            ("Amit Verma", "amit@sports.edu", hash_password("amit123"), "student", 0),
        ]
        cursor.executemany(
            "INSERT INTO users (name, email, hashed_password, role, is_blocked) VALUES (?, ?, ?, ?, ?)",
            users
        )

    # Check if sports already seeded
    cursor.execute("SELECT COUNT(*) as count FROM sports")
    if cursor.fetchone()["count"] == 0:
        sports = [
            ("Cricket", "Outdoor", "11-a-side pitch with batting and bowling nets", 11, 22),
            ("Badminton", "Racket", "Indoor wooden synthetic court with international nets", 2, 4),
            ("Basketball", "Indoor", "Full size maple-wood basketball court with electronic scoreboard", 5, 10),
            ("Football", "Outdoor", "FIFA standard natural grass football arena", 11, 22),
            ("Table Tennis", "Indoor", "ITTF approved tables with tournament grade lighting", 2, 4),
            ("Swimming", "Aquatic", "50m Olympic size 8-lane heated swimming pool", 1, 20),
        ]
        cursor.executemany(
            "INSERT INTO sports (name, category, description, min_players, max_players) VALUES (?, ?, ?, ?, ?)",
            sports
        )

    # Check if facilities already seeded
    cursor.execute("SELECT COUNT(*) as count FROM facilities")
    if cursor.fetchone()["count"] == 0:
        facilities = [
            ("Main Cricket Stadium", 1, "North Campus Ground A", 30, 1),
            ("Badminton Court 1", 2, "Indoor Sports Complex Level 1", 4, 1),
            ("Badminton Court 2", 2, "Indoor Sports Complex Level 1", 4, 1),
            ("Central Basketball Arena", 3, "East Sports Block", 15, 1),
            ("Football Turf Field", 4, "South Stadium", 25, 1),
            ("Olympic Aquatic Pool", 6, "Aquatics Center", 20, 1),
            ("Table Tennis Hall - Table 1", 5, "Recreation Center L2", 4, 1),
        ]
        cursor.executemany(
            "INSERT INTO facilities (name, sport_id, location, capacity, is_available) VALUES (?, ?, ?, ?, ?)",
            facilities
        )

    # Check if bookings already seeded
    cursor.execute("SELECT COUNT(*) as count FROM bookings")
    if cursor.fetchone()["count"] == 0:
        today_str = date.today().isoformat()
        bookings = [
            (2, 2, 2, today_str, "06:00 - 07:00", "confirmed", "Morning practice session"),
            (3, 1, 1, today_str, "07:00 - 08:00", "confirmed", "Cricket team trial"),
            (2, 4, 3, today_str, "17:00 - 18:00", "confirmed", "Friendly match"),
            (4, 6, 6, today_str, "18:00 - 19:00", "confirmed", "Swimming endurance drills"),
        ]
        cursor.executemany(
            "INSERT INTO bookings (user_id, facility_id, sport_id, booking_date, time_slot, status, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            bookings
        )

    # Check if attendance already seeded
    cursor.execute("SELECT COUNT(*) as count FROM attendance")
    if cursor.fetchone()["count"] == 0:
        attendance = [
            (1, 2, "present", 1),
            (2, 3, "present", 1),
        ]
        cursor.executemany(
            "INSERT INTO attendance (booking_id, user_id, status, marked_by) VALUES (?, ?, ?, ?)",
            attendance
        )

    conn.commit()
