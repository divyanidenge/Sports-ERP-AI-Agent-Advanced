import sqlite3
from datetime import date, datetime
from typing import List, Optional
from fastapi import HTTPException, status
from app.database import get_db_connection
from app.models import (
    SportCreate, SportResponse,
    FacilityCreate, FacilityResponse,
    BookingCreate, BookingResponse,
    AttendanceCreate, AttendanceResponse,
    DashboardStats
)

# --- SPORTS SERVICE ---
def list_sports() -> List[SportResponse]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, category, description, min_players, max_players, created_at FROM sports ORDER BY name ASC")
    rows = cursor.fetchall()
    conn.close()
    return [SportResponse(**dict(row)) for row in rows]

def create_sport(data: SportCreate) -> SportResponse:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO sports (name, category, description, min_players, max_players) VALUES (?, ?, ?, ?, ?)",
            (data.name.strip(), data.category.strip(), data.description.strip() if data.description else "", data.min_players, data.max_players)
        )
        conn.commit()
        sport_id = cursor.lastrowid
        cursor.execute("SELECT id, name, category, description, min_players, max_players, created_at FROM sports WHERE id = ?", (sport_id,))
        row = cursor.fetchone()
        conn.close()
        return SportResponse(**dict(row))
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Sport with name '{data.name}' already exists.")

def delete_sport(sport_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM sports WHERE id = ?", (sport_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sport not found.")
    cursor.execute("DELETE FROM sports WHERE id = ?", (sport_id,))
    conn.commit()
    conn.close()
    return {"message": f"Sport ID {sport_id} deleted successfully."}

# --- FACILITIES SERVICE ---
def list_facilities() -> List[FacilityResponse]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT f.id, f.name, f.sport_id, s.name as sport_name, f.location, f.capacity, f.is_available, f.created_at
        FROM facilities f
        LEFT JOIN sports s ON f.sport_id = s.id
        ORDER BY f.id ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [FacilityResponse(**dict(row)) for row in rows]

def create_facility(data: FacilityCreate) -> FacilityResponse:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if sport exists
    cursor.execute("SELECT name FROM sports WHERE id = ?", (data.sport_id,))
    sport_row = cursor.fetchone()
    if not sport_row:
        conn.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referenced sport does not exist.")
    
    cursor.execute(
        "INSERT INTO facilities (name, sport_id, location, capacity, is_available) VALUES (?, ?, ?, ?, ?)",
        (data.name.strip(), data.sport_id, data.location.strip(), data.capacity, data.is_available)
    )
    conn.commit()
    fac_id = cursor.lastrowid
    
    cursor.execute("""
        SELECT f.id, f.name, f.sport_id, s.name as sport_name, f.location, f.capacity, f.is_available, f.created_at
        FROM facilities f
        LEFT JOIN sports s ON f.sport_id = s.id
        WHERE f.id = ?
    """, (fac_id,))
    row = cursor.fetchone()
    conn.close()
    return FacilityResponse(**dict(row))

def toggle_facility_status(facility_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, is_available FROM facilities WHERE id = ?", (facility_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Facility not found.")
    
    new_status = 0 if row["is_available"] == 1 else 1
    cursor.execute("UPDATE facilities SET is_available = ? WHERE id = ?", (new_status, facility_id))
    conn.commit()
    conn.close()
    return {"message": f"Facility ID {facility_id} availability set to {new_status}.", "is_available": new_status}

# --- BOOKINGS SERVICE ---
def create_booking(user_id: int, data: BookingCreate) -> BookingResponse:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check facility
    cursor.execute("SELECT id, is_available, sport_id FROM facilities WHERE id = ?", (data.facility_id,))
    fac = cursor.fetchone()
    if not fac:
        conn.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Facility not found.")
    if fac["is_available"] == 0:
        conn.close()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Facility is currently marked unavailable for booking.")
    
    # Check conflict
    cursor.execute(
        "SELECT id FROM bookings WHERE facility_id = ? AND booking_date = ? AND time_slot = ? AND status = 'confirmed'",
        (data.facility_id, data.booking_date, data.time_slot)
    )
    if cursor.fetchone():
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Facility is already booked for date {data.booking_date} at slot {data.time_slot}."
        )
    
    cursor.execute(
        "INSERT INTO bookings (user_id, facility_id, sport_id, booking_date, time_slot, status, notes) VALUES (?, ?, ?, ?, ?, 'confirmed', ?)",
        (user_id, data.facility_id, data.sport_id, data.booking_date, data.time_slot, data.notes or "")
    )
    conn.commit()
    booking_id = cursor.lastrowid
    
    cursor.execute("""
        SELECT b.id, b.user_id, u.name as user_name, u.email as user_email,
               b.facility_id, f.name as facility_name,
               b.sport_id, s.name as sport_name,
               b.booking_date, b.time_slot, b.status, b.notes, b.created_at
        FROM bookings b
        LEFT JOIN users u ON b.user_id = u.id
        LEFT JOIN facilities f ON b.facility_id = f.id
        LEFT JOIN sports s ON b.sport_id = s.id
        WHERE b.id = ?
    """, (booking_id,))
    row = cursor.fetchone()
    conn.close()
    return BookingResponse(**dict(row))

def list_user_bookings(user_id: int) -> List[BookingResponse]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.id, b.user_id, u.name as user_name, u.email as user_email,
               b.facility_id, f.name as facility_name,
               b.sport_id, s.name as sport_name,
               b.booking_date, b.time_slot, b.status, b.notes, b.created_at
        FROM bookings b
        LEFT JOIN users u ON b.user_id = u.id
        LEFT JOIN facilities f ON b.facility_id = f.id
        LEFT JOIN sports s ON b.sport_id = s.id
        WHERE b.user_id = ?
        ORDER BY b.booking_date DESC, b.time_slot DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [BookingResponse(**dict(row)) for row in rows]

def list_all_bookings() -> List[BookingResponse]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.id, b.user_id, u.name as user_name, u.email as user_email,
               b.facility_id, f.name as facility_name,
               b.sport_id, s.name as sport_name,
               b.booking_date, b.time_slot, b.status, b.notes, b.created_at
        FROM bookings b
        LEFT JOIN users u ON b.user_id = u.id
        LEFT JOIN facilities f ON b.facility_id = f.id
        LEFT JOIN sports s ON b.sport_id = s.id
        ORDER BY b.booking_date DESC, b.time_slot DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [BookingResponse(**dict(row)) for row in rows]

def cancel_booking(booking_id: int, user_id: int, is_admin: bool = False):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, status FROM bookings WHERE id = ?", (booking_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")
    
    if not is_admin and row["user_id"] != user_id:
        conn.close()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only cancel your own bookings.")
    
    cursor.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking_id,))
    conn.commit()
    conn.close()
    return {"message": f"Booking #{booking_id} cancelled successfully."}

# --- ATTENDANCE SERVICE ---
def mark_attendance(data: AttendanceCreate, marked_by: int) -> AttendanceResponse:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if booking exists
    cursor.execute("SELECT id, user_id FROM bookings WHERE id = ?", (data.booking_id,))
    b_row = cursor.fetchone()
    if not b_row:
        conn.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking does not exist.")
    
    cursor.execute(
        "INSERT INTO attendance (booking_id, user_id, status, marked_by) VALUES (?, ?, ?, ?)",
        (data.booking_id, data.user_id, data.status, marked_by)
    )
    conn.commit()
    att_id = cursor.lastrowid
    
    cursor.execute("""
        SELECT a.id, a.booking_id, a.user_id, u.name as user_name,
               a.check_in_time, a.status, a.marked_by, m.name as marked_by_name,
               b.booking_date, b.time_slot, f.name as facility_name, s.name as sport_name
        FROM attendance a
        LEFT JOIN users u ON a.user_id = u.id
        LEFT JOIN users m ON a.marked_by = m.id
        LEFT JOIN bookings b ON a.booking_id = b.id
        LEFT JOIN facilities f ON b.facility_id = f.id
        LEFT JOIN sports s ON b.sport_id = s.id
        WHERE a.id = ?
    """, (att_id,))
    row = cursor.fetchone()
    conn.close()
    return AttendanceResponse(**dict(row))

def list_attendance() -> List[AttendanceResponse]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.booking_id, a.user_id, u.name as user_name,
               a.check_in_time, a.status, a.marked_by, m.name as marked_by_name,
               b.booking_date, b.time_slot, f.name as facility_name, s.name as sport_name
        FROM attendance a
        LEFT JOIN users u ON a.user_id = u.id
        LEFT JOIN users m ON a.marked_by = m.id
        LEFT JOIN bookings b ON a.booking_id = b.id
        LEFT JOIN facilities f ON b.facility_id = f.id
        LEFT JOIN sports s ON b.sport_id = s.id
        ORDER BY a.check_in_time DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [AttendanceResponse(**dict(row)) for row in rows]

def list_user_attendance(user_id: int) -> List[AttendanceResponse]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.booking_id, a.user_id, u.name as user_name,
               a.check_in_time, a.status, a.marked_by, m.name as marked_by_name,
               b.booking_date, b.time_slot, f.name as facility_name, s.name as sport_name
        FROM attendance a
        LEFT JOIN users u ON a.user_id = u.id
        LEFT JOIN users m ON a.marked_by = m.id
        LEFT JOIN bookings b ON a.booking_id = b.id
        LEFT JOIN facilities f ON b.facility_id = f.id
        LEFT JOIN sports s ON b.sport_id = s.id
        WHERE a.user_id = ?
        ORDER BY a.check_in_time DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [AttendanceResponse(**dict(row)) for row in rows]

# --- DASHBOARD SERVICE ---
def get_dashboard_overview() -> DashboardStats:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    today_str = date.today().isoformat()
    
    cursor.execute("SELECT COUNT(*) as count FROM users")
    total_users = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE role = 'student' AND is_blocked = 0")
    active_students = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM sports")
    total_sports = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM facilities")
    total_facilities = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM bookings")
    total_bookings = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM bookings WHERE booking_date = ?", (today_str,))
    today_bookings = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM attendance WHERE status = 'present'")
    present_count = cursor.fetchone()["count"]
    
    attendance_rate = round((present_count / total_bookings * 100) if total_bookings > 0 else 100.0, 1)
    
    cursor.execute("""
        SELECT b.id, u.name as user_name, f.name as facility_name, s.name as sport_name,
               b.booking_date, b.time_slot, b.status
        FROM bookings b
        LEFT JOIN users u ON b.user_id = u.id
        LEFT JOIN facilities f ON b.facility_id = f.id
        LEFT JOIN sports s ON b.sport_id = s.id
        ORDER BY b.id DESC LIMIT 5
    """)
    recent_bookings = [dict(r) for r in cursor.fetchall()]
    conn.close()
    
    return DashboardStats(
        total_users=total_users,
        active_students=active_students,
        total_sports=total_sports,
        total_facilities=total_facilities,
        total_bookings=total_bookings,
        today_bookings=today_bookings,
        attendance_rate=attendance_rate,
        recent_bookings=recent_bookings
    )
