import sqlite3
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from fastapi import HTTPException, status
from app.database import get_db_connection
from app.models import (
    SportCreate, SportResponse,
    FacilityCreate, FacilityResponse,
    BookingCreate, BookingResponse,
    AttendanceCreate, AttendanceResponse,
    DashboardStats, AdvancedAnalytics
)
from app.audit_service import log_audit_event

ALL_STANDARD_SLOTS = [
    "06:00 - 07:00",
    "07:00 - 08:00",
    "08:00 - 09:00",
    "16:00 - 17:00",
    "17:00 - 18:00",
    "18:00 - 19:00",
    "19:00 - 20:00"
]

def parse_slot_start_hour(slot_str: str) -> int:
    """Extract integer start hour from time slot string e.g. '17:00 - 18:00' -> 17."""
    try:
        start_part = slot_str.split("-")[0].strip()
        hour_part = start_part.split(":")[0].strip()
        return int(hour_part)
    except Exception:
        return 12

def rank_slots_by_proximity(available_slots: List[str], requested_slot: Optional[str] = None, slot_capacities: Optional[Dict[str, int]] = None) -> List[str]:
    """
    Ranks available slots deterministically:
    1. Proximity to requested hour (closest absolute difference in hours first)
    2. Available court capacity (slots with more open courts first)
    3. Chronological order (earlier slots first)
    """
    if not available_slots:
        return []
    
    if not requested_slot:
        return sorted(available_slots)
    
    req_hour = parse_slot_start_hour(requested_slot)
    
    def ranking_key(slot):
        slot_hour = parse_slot_start_hour(slot)
        proximity = abs(slot_hour - req_hour)
        capacity = (slot_capacities.get(slot, 1) if slot_capacities else 1)
        return (proximity, -capacity, slot_hour)
    
    return sorted(available_slots, key=ranking_key)

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
        
        log_audit_event(
            action="SPORT_CREATED",
            resource_type="sport",
            resource_id=sport_id,
            details=f"Created sport '{data.name.strip()}' in category '{data.category.strip()}'"
        )
        
        return SportResponse(**dict(row))
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Sport with name '{data.name}' already exists.")

def delete_sport(sport_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM sports WHERE id = ?", (sport_id,))
    sport_row = cursor.fetchone()
    if not sport_row:
        conn.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sport not found.")
    
    sport_name = sport_row["name"]
    cursor.execute("DELETE FROM sports WHERE id = ?", (sport_id,))
    conn.commit()
    conn.close()
    
    log_audit_event(
        action="SPORT_DELETED",
        resource_type="sport",
        resource_id=sport_id,
        details=f"Deleted sport '{sport_name}' (ID #{sport_id})"
    )
    
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
    
    log_audit_event(
        action="FACILITY_CREATED",
        resource_type="facility",
        resource_id=fac_id,
        details=f"Created facility '{data.name.strip()}' for sport '{sport_row['name']}'"
    )
    
    return FacilityResponse(**dict(row))

def toggle_facility_status(facility_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, is_available FROM facilities WHERE id = ?", (facility_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Facility not found.")
    
    new_status = 0 if row["is_available"] == 1 else 1
    cursor.execute("UPDATE facilities SET is_available = ? WHERE id = ?", (new_status, facility_id))
    conn.commit()
    conn.close()
    
    log_audit_event(
        action="FACILITY_STATUS_TOGGLED",
        resource_type="facility",
        resource_id=facility_id,
        details=f"Facility '{row['name']}' availability updated to {new_status}"
    )
    
    return {"message": f"Facility ID {facility_id} availability set to {new_status}.", "is_available": new_status}

# --- BOOKINGS SERVICE ---
def create_booking(user_id: int, data: BookingCreate) -> BookingResponse:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Idempotency Check: if idempotency key is provided and already exists, return existing booking
    if data.idempotency_key:
        cursor.execute("""
            SELECT b.id, b.user_id, u.name as user_name, u.email as user_email,
                   b.facility_id, f.name as facility_name,
                   b.sport_id, s.name as sport_name,
                   b.booking_date, b.time_slot, b.status, b.notes, b.idempotency_key, b.created_at
            FROM bookings b
            LEFT JOIN users u ON b.user_id = u.id
            LEFT JOIN facilities f ON b.facility_id = f.id
            LEFT JOIN sports s ON b.sport_id = s.id
            WHERE b.idempotency_key = ?
        """, (data.idempotency_key.strip(),))
        existing = cursor.fetchone()
        if existing:
            conn.close()
            return BookingResponse(**dict(existing))

    # 2. Enforce Student Daily Quota Limit (Rule C6: Max 2 bookings per day per student)
    cursor.execute("SELECT role FROM users WHERE id = ?", (user_id,))
    u_row = cursor.fetchone()
    if u_row and u_row["role"] != "admin":
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM bookings WHERE user_id = ? AND booking_date = ? AND status = 'confirmed'",
            (user_id, data.booking_date)
        )
        d_cnt = cursor.fetchone()["cnt"]
        if d_cnt >= 2:
            conn.close()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Daily booking quota exceeded: Students can hold a maximum of 2 bookings per day on {data.booking_date}."
            )

    # 3. Check facility availability
    cursor.execute("SELECT id, name, is_available, sport_id FROM facilities WHERE id = ?", (data.facility_id,))
    fac = cursor.fetchone()
    if not fac:
        conn.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Facility not found.")
    if fac["is_available"] == 0:
        conn.close()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Facility is currently marked unavailable for booking.")
    
    # 3. Check conflict (Pre-check)
    cursor.execute(
        "SELECT id FROM bookings WHERE facility_id = ? AND booking_date = ? AND time_slot = ? AND status = 'confirmed'",
        (data.facility_id, data.booking_date, data.time_slot)
    )
    if cursor.fetchone():
        conn.close()
        log_audit_event(
            action="BOOKING_CONFLICT",
            status="FAILED",
            user_id=user_id,
            resource_type="facility",
            resource_id=data.facility_id,
            details=f"Facility #{data.facility_id} is already booked on {data.booking_date} at slot {data.time_slot}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Facility is already booked for date {data.booking_date} at slot {data.time_slot}."
        )
    
    # 4. Atomic Insert with Concurrency Protection (Unique Partial Index Guard)
    try:
        cursor.execute(
            "INSERT INTO bookings (user_id, facility_id, sport_id, booking_date, time_slot, status, notes, idempotency_key) VALUES (?, ?, ?, ?, ?, 'confirmed', ?, ?)",
            (user_id, data.facility_id, data.sport_id, data.booking_date, data.time_slot, data.notes or "", data.idempotency_key.strip() if data.idempotency_key else None)
        )
        conn.commit()
        booking_id = cursor.lastrowid
    except sqlite3.IntegrityError as ie:
        conn.rollback()
        conn.close()
        log_audit_event(
            action="BOOKING_CONFLICT",
            status="FAILED",
            user_id=user_id,
            resource_type="facility",
            resource_id=data.facility_id,
            details=f"Concurrency collision on facility #{data.facility_id} on {data.booking_date} at {data.time_slot}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Facility is already booked for date {data.booking_date} at slot {data.time_slot}."
        )
    
    cursor.execute("""
        SELECT b.id, b.user_id, u.name as user_name, u.email as user_email,
               b.facility_id, f.name as facility_name,
               b.sport_id, s.name as sport_name,
               b.booking_date, b.time_slot, b.status, b.notes, b.idempotency_key, b.created_at
        FROM bookings b
        LEFT JOIN users u ON b.user_id = u.id
        LEFT JOIN facilities f ON b.facility_id = f.id
        LEFT JOIN sports s ON b.sport_id = s.id
        WHERE b.id = ?
    """, (booking_id,))
    row = cursor.fetchone()
    conn.close()
    
    log_audit_event(
        action="BOOKING_CREATED",
        user_id=user_id,
        resource_type="booking",
        resource_id=booking_id,
        details=f"Booking #{booking_id} created for facility '{fac['name']}' on {data.booking_date} ({data.time_slot})"
    )
    
    return BookingResponse(**dict(row))

def list_user_bookings(user_id: int) -> List[BookingResponse]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.id, b.user_id, u.name as user_name, u.email as user_email,
               b.facility_id, f.name as facility_name,
               b.sport_id, s.name as sport_name,
               b.booking_date, b.time_slot, b.status, b.notes, b.idempotency_key, b.created_at
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
               b.booking_date, b.time_slot, b.status, b.notes, b.idempotency_key, b.created_at
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
    cursor.execute("SELECT id, user_id, facility_id, booking_date, time_slot, status FROM bookings WHERE id = ?", (booking_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")
    
    if not is_admin and row["user_id"] != user_id:
        conn.close()
        log_audit_event(
            action="ACCESS_DENIED",
            status="DENIED",
            user_id=user_id,
            resource_type="booking",
            resource_id=booking_id,
            details=f"Unauthorized cancellation attempt on booking #{booking_id} owned by user #{row['user_id']}"
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only cancel your own bookings.")
    
    cursor.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking_id,))
    conn.commit()
    conn.close()
    
    log_audit_event(
        action="BOOKING_CANCELLED",
        user_id=user_id,
        resource_type="booking",
        resource_id=booking_id,
        details=f"Booking #{booking_id} cancelled on {row['booking_date']} ({row['time_slot']})"
    )
    
    return {"message": f"Booking #{booking_id} cancelled successfully."}

def restore_booking(booking_id: int, user_id: int, is_admin: bool = False) -> Dict[str, Any]:
    """Restores a cancelled booking after validating ownership, availability, constraints, and audit logging."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.id, b.user_id, b.facility_id, b.sport_id, b.booking_date, b.time_slot, b.status,
               f.name as facility_name, f.is_available as fac_available, s.name as sport_name
        FROM bookings b
        LEFT JOIN facilities f ON b.facility_id = f.id
        LEFT JOIN sports s ON b.sport_id = s.id
        WHERE b.id = ?
    """, (booking_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Booking #{booking_id} not found.")
    
    # Ownership verification
    if not is_admin and row["user_id"] != user_id:
        conn.close()
        log_audit_event(
            action="ACCESS_DENIED",
            status="DENIED",
            user_id=user_id,
            resource_type="booking",
            resource_id=booking_id,
            details=f"Unauthorized restore attempt on booking #{booking_id} owned by user #{row['user_id']}"
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only restore your own bookings.")
    
    # State verification: Must be currently cancelled
    if row["status"] != "cancelled":
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Booking #{booking_id} is currently '{row['status']}' and cannot be restored."
        )
    
    # Facility operational status
    if row["fac_available"] == 0:
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot restore booking: Facility '{row['facility_name']}' is currently inactive or closed for maintenance."
        )

    # Temporal validity: Cannot restore past dates
    today_iso = date.today().isoformat()
    if row["booking_date"] < today_iso:
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot restore booking #{booking_id} because date '{row['booking_date']}' is in the past."
        )

    # Rule C6: Student daily limit check (max 2 active bookings per day)
    cursor.execute("SELECT role FROM users WHERE id = ?", (row["user_id"],))
    u_row = cursor.fetchone()
    u_role = u_row["role"] if u_row else "student"
    if u_role != "admin":
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM bookings WHERE user_id = ? AND booking_date = ? AND status = 'confirmed'",
            (row["user_id"], row["booking_date"])
        )
        d_cnt = cursor.fetchone()["cnt"]
        if d_cnt >= 2:
            conn.close()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot restore booking #{booking_id}: Daily quota of 2 confirmed bookings on {row['booking_date']} already reached."
            )

    # Check slot conflict with existing active bookings
    cursor.execute(
        "SELECT id FROM bookings WHERE facility_id = ? AND booking_date = ? AND time_slot = ? AND status = 'confirmed'",
        (row["facility_id"], row["booking_date"], row["time_slot"])
    )
    if cursor.fetchone():
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot restore booking #{booking_id}: Facility '{row['facility_name']}' is already booked on {row['booking_date']} at slot {row['time_slot']}."
        )

    # Atomic Update with concurrency guard
    try:
        cursor.execute("UPDATE bookings SET status = 'confirmed' WHERE id = ?", (booking_id,))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot restore booking #{booking_id}: Slot conflict collision on {row['booking_date']} at {row['time_slot']}."
        )
    conn.close()

    # Log cryptographic provenance audit event
    log_audit_event(
        action="BOOKING_RESTORED",
        user_id=user_id,
        resource_type="booking",
        resource_id=booking_id,
        details=f"Booking #{booking_id} restored to confirmed status for {row['facility_name']} on {row['booking_date']} ({row['time_slot']})"
    )

    return {
        "success": True,
        "message": f"Booking #{booking_id} ({row['sport_name']} at {row['facility_name']} on {row['booking_date']} at {row['time_slot']}) has been restored successfully.",
        "booking_id": booking_id
    }

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
    
    log_audit_event(
        action="ATTENDANCE_MARKED",
        user_id=marked_by,
        resource_type="attendance",
        resource_id=att_id,
        details=f"Attendance for user #{data.user_id} on booking #{data.booking_id} marked as '{data.status}'"
    )
    
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

# --- DASHBOARD & ANALYTICS SERVICE ---
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
    
    attendance_rate = round((present_count / total_bookings * 100) if total_bookings > 0 else 0.0, 1)
    
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

def get_advanced_analytics() -> AdvancedAnalytics:
    """Calculates comprehensive database-derived Sports ERP metrics."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Booking counts
    cursor.execute("SELECT COUNT(*) as count FROM bookings")
    total_bookings = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM bookings WHERE status = 'confirmed'")
    active_confirmed = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM bookings WHERE status = 'cancelled'")
    cancelled_bookings = cursor.fetchone()["count"]
    
    cancellation_rate = round((cancelled_bookings / total_bookings * 100) if total_bookings > 0 else 0.0, 1)
    
    # 2. Attendance metrics
    cursor.execute("SELECT COUNT(*) as count FROM attendance")
    total_attendance = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM attendance WHERE status = 'present'")
    present_attendance = cursor.fetchone()["count"]
    
    attendance_present_rate = round((present_attendance / total_attendance * 100) if total_attendance > 0 else 0.0, 1)
    
    # 3. Facility Utilization Rate (confirmed bookings / total theoretical capacity across 7 slots)
    cursor.execute("SELECT COUNT(*) as count FROM facilities WHERE is_available = 1")
    active_fac_count = cursor.fetchone()["count"]
    
    # Theoretical capacity = active_fac_count * 7 daily slots
    daily_slot_capacity = max(1, active_fac_count * len(ALL_STANDARD_SLOTS))
    facility_utilization_rate = round(min(100.0, (active_confirmed / daily_slot_capacity * 100)), 1)
    
    # 4. Popular Sports Ranking
    cursor.execute("""
        SELECT s.id, s.name, s.category, COUNT(b.id) as booking_count
        FROM sports s
        LEFT JOIN bookings b ON s.id = b.sport_id
        GROUP BY s.id
        ORDER BY booking_count DESC, s.name ASC
    """)
    popular_sports = []
    for r in cursor.fetchall():
        b_count = r["booking_count"]
        pct = round((b_count / total_bookings * 100) if total_bookings > 0 else 0.0, 1)
        popular_sports.append({
            "sport_id": r["id"],
            "sport_name": r["name"],
            "category": r["category"],
            "booking_count": b_count,
            "percentage": pct
        })
    
    # 5. Peak Hours Distribution
    cursor.execute("""
        SELECT time_slot, COUNT(*) as count
        FROM bookings
        WHERE status = 'confirmed'
        GROUP BY time_slot
        ORDER BY count DESC
    """)
    peak_hours_distribution = []
    for r in cursor.fetchall():
        peak_hours_distribution.append({
            "time_slot": r["time_slot"],
            "booking_count": r["count"]
        })
    
    # 6. Facility Breakdown
    cursor.execute("""
        SELECT f.id, f.name as facility_name, s.name as sport_name, f.location,
               COUNT(b.id) as total_bookings,
               SUM(CASE WHEN b.status = 'confirmed' THEN 1 ELSE 0 END) as active_bookings
        FROM facilities f
        LEFT JOIN sports s ON f.sport_id = s.id
        LEFT JOIN bookings b ON f.id = b.facility_id
        GROUP BY f.id
        ORDER BY f.id ASC
    """)
    facility_breakdown = []
    for r in cursor.fetchall():
        facility_breakdown.append({
            "facility_id": r["id"],
            "facility_name": r["facility_name"],
            "sport_name": r["sport_name"],
            "location": r["location"],
            "total_bookings": r["total_bookings"] or 0,
            "active_bookings": r["active_bookings"] or 0
        })
    
    conn.close()
    
    return AdvancedAnalytics(
        total_bookings=total_bookings,
        active_confirmed_bookings=active_confirmed,
        cancelled_bookings=cancelled_bookings,
        cancellation_rate=cancellation_rate,
        total_attendance_records=total_attendance,
        attendance_present_rate=attendance_present_rate,
        facility_utilization_rate=facility_utilization_rate,
        popular_sports=popular_sports,
        peak_hours_distribution=peak_hours_distribution,
        facility_breakdown=facility_breakdown
    )

