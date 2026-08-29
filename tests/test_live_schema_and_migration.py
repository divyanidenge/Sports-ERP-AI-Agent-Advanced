import pytest
import sqlite3
import tempfile
import os
from app.database import migrate_db, hash_password
from app.models import BookingCreate
import app.sports_service as sports_service

def test_migration_on_legacy_schema_without_data_loss():
    """
    Test:
    1. Create a legacy SQLite database mimicking pre-migration schema (missing idempotency_key).
    2. Insert sample user and booking rows.
    3. Run migrate_db().
    4. Assert idempotency_key column and indexes are added.
    5. Assert existing user and booking data are 100% preserved.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        legacy_db_path = f.name

    try:
        conn = sqlite3.connect(legacy_db_path)
        cursor = conn.cursor()
        
        # Create old schema
        cursor.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student'
        )
        """)
        cursor.execute("""
        CREATE TABLE sports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL
        )
        """)
        cursor.execute("""
        CREATE TABLE facilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sport_id INTEGER NOT NULL,
            location TEXT NOT NULL,
            capacity INTEGER DEFAULT 10,
            is_available INTEGER DEFAULT 1
        )
        """)
        cursor.execute("""
        CREATE TABLE bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            facility_id INTEGER NOT NULL,
            sport_id INTEGER NOT NULL,
            booking_date TEXT NOT NULL,
            time_slot TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'confirmed',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Insert legacy seed data
        cursor.execute("INSERT INTO users (name, email, hashed_password, role) VALUES ('Legacy User', 'legacy@sports.edu', 'hash123', 'student')")
        cursor.execute("INSERT INTO sports (name, category) VALUES ('Badminton', 'Racket')")
        cursor.execute("INSERT INTO facilities (name, sport_id, location, capacity, is_available) VALUES ('Court 1', 1, 'Hall A', 4, 1)")
        cursor.execute("INSERT INTO bookings (user_id, facility_id, sport_id, booking_date, time_slot, status, notes) VALUES (1, 1, 1, '2026-10-01', '06:00 - 07:00', 'confirmed', 'Legacy booking')")
        conn.commit()

        # Verify old table has no idempotency_key
        cursor.execute("PRAGMA table_info(bookings)")
        cols_before = [r[1] for r in cursor.fetchall()]
        assert "idempotency_key" not in cols_before

        # Execute Migration
        migrate_db(conn)

        # Verify idempotency_key and is_blocked exist now
        cursor.execute("PRAGMA table_info(bookings)")
        cols_after = [r[1] for r in cursor.fetchall()]
        assert "idempotency_key" in cols_after

        cursor.execute("PRAGMA table_info(users)")
        u_cols_after = [r[1] for r in cursor.fetchall()]
        assert "is_blocked" in u_cols_after

        # Verify data rows preserved
        cursor.execute("SELECT COUNT(*) FROM bookings")
        assert cursor.fetchone()[0] == 1

        cursor.execute("SELECT COUNT(*) FROM users")
        assert cursor.fetchone()[0] == 1

        # Verify index exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_active_facility_booking'")
        assert cursor.fetchone() is not None

        conn.close()
    finally:
        try:
            conn.close()
        except Exception:
            pass
        if os.path.exists(legacy_db_path):
            try:
                os.remove(legacy_db_path)
            except Exception:
                pass
