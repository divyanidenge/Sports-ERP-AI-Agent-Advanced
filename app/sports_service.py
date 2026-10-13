import sqlite3
import uuid
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from fastapi import HTTPException, status
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD
from app.database import get_db_connection
from app.models import (
    SportCreate, SportResponse,
    FacilityCreate, FacilityResponse,
    BookingCreate, BookingResponse, BookingReschedule,
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
        SELECT f.id, f.name, f.sport_id, s.name as sport_name, f.location, f.capacity, f.is_available, f.open_time, f.close_time, f.created_at
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
        "INSERT INTO facilities (name, sport_id, location, capacity, is_available, open_time, close_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (data.name.strip(), data.sport_id, data.location.strip(), data.capacity, data.is_available, data.open_time, data.close_time)
    )
    conn.commit()
    fac_id = cursor.lastrowid
    
    cursor.execute("""
        SELECT f.id, f.name, f.sport_id, s.name as sport_name, f.location, f.capacity, f.is_available, f.open_time, f.close_time, f.created_at
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
    today_iso = date.today().isoformat()
    if data.booking_date < today_iso:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create bookings for past dates."
        )
        
    computed_time_slot = f"{data.start_time} - {data.end_time}"
    
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
    cursor.execute("SELECT id, name, is_available, sport_id, open_time, close_time FROM facilities WHERE id = ?", (data.facility_id,))
    fac = cursor.fetchone()
    if not fac:
        conn.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Facility not found.")
    if fac["is_available"] == 0:
        conn.close()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Facility is currently marked unavailable for booking.")
    
    eff_data_end = "24:00" if data.end_time == "00:00" else data.end_time
    eff_fac_close = "24:00" if fac["close_time"] == "00:00" else fac["close_time"]
    if data.start_time < fac["open_time"] or eff_data_end > eff_fac_close:
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Requested slot {data.start_time} - {data.end_time} is outside facility operating hours ({fac['open_time']} - {fac['close_time']})."
        )
    
    if data.start_time >= eff_data_end:
        conn.close()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Start time must be before end time.")

    # 4. Check conflict (Overlap Logic)
    cursor.execute(
        "SELECT id, time_slot FROM bookings WHERE facility_id = ? AND booking_date = ? AND status = 'confirmed'",
        (data.facility_id, data.booking_date)
    )
    existing_bookings = cursor.fetchall()
    for eb in existing_bookings:
        try:
            eb_start, eb_end = eb["time_slot"].split(" - ")
            if data.start_time < eb_end and data.end_time > eb_start:
                conn.close()
                log_audit_event(
                    action="BOOKING_CONFLICT",
                    status="FAILED",
                    user_id=user_id,
                    resource_type="facility",
                    resource_id=data.facility_id,
                    details=f"Facility #{data.facility_id} overlaps with existing booking {eb['time_slot']} on {data.booking_date}"
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail=f"Time slot overlaps with an existing booking: {eb['time_slot']}."
                )
        except ValueError:
            pass
    
    # 4. Atomic Insert with Concurrency Protection (Unique Partial Index Guard)
    qr_code = uuid.uuid4().hex
    try:
        cursor.execute(
            "INSERT INTO bookings (user_id, facility_id, sport_id, booking_date, time_slot, status, notes, idempotency_key, qr_code) VALUES (?, ?, ?, ?, ?, 'confirmed', ?, ?, ?)",
            (user_id, data.facility_id, data.sport_id, data.booking_date, computed_time_slot, data.notes or "", data.idempotency_key.strip() if data.idempotency_key else None, qr_code)
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
            details=f"Concurrency collision on facility #{data.facility_id} on {data.booking_date} at {computed_time_slot}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Facility is already booked for date {data.booking_date} at slot {computed_time_slot}."
        )
    
    # Send Email Notification
    def send_qr_email(user_email, booking_id, qr_code, facility, date, slot):
        if not SMTP_HOST or not SMTP_USERNAME:
            print("SMTP configuration not found. Skipping real email.")
            return

        subject = f"Your Sports Booking Confirmation & QR Ticket (#{booking_id})"
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f3f4f6;">
            <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
                <tr>
                    <td style="padding: 20px 0 30px 0;">
                        <table align="center" border="0" cellpadding="0" cellspacing="0" width="600" style="background-color: #ffffff; border-radius: 8px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); border: 1px solid #e5e7eb; border-collapse: collapse;">
                            <!-- Header -->
                            <tr>
                                <td align="center" style="padding: 30px 0 20px 0; background-color: #1e3a8a; border-radius: 8px 8px 0 0;">
                                    <h1 style="color: #ffffff; font-size: 24px; margin: 0; letter-spacing: 1px;">CAMPUS SPORTS ERP</h1>
                                    <p style="color: #bfdbfe; font-size: 14px; margin: 5px 0 0 0;">Booking Confirmation & Entry Ticket</p>
                                </td>
                            </tr>
                            
                            <!-- Body -->
                            <tr>
                                <td style="padding: 30px 40px 10px 40px;">
                                    <h2 style="color: #1f2937; font-size: 20px; margin: 0 0 15px 0;">Hello!</h2>
                                    <p style="color: #4b5563; font-size: 16px; line-height: 24px; margin: 0 0 20px 0;">
                                        Your sports facility reservation has been confirmed. Below are your booking details and the QR code ticket for entry.
                                    </p>
                                    
                                    <!-- Details Box -->
                                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; margin-bottom: 25px;">
                                        <tr>
                                            <td style="padding: 20px;">
                                                <p style="margin: 0 0 10px 0; font-size: 15px; color: #334155;"><strong>Booking ID:</strong> #{booking_id}</p>
                                                <p style="margin: 0 0 10px 0; font-size: 15px; color: #334155;"><strong>Facility:</strong> {facility}</p>
                                                <p style="margin: 0 0 10px 0; font-size: 15px; color: #334155;"><strong>Date:</strong> {date}</p>
                                                <p style="margin: 0; font-size: 15px; color: #334155;"><strong>Time Slot:</strong> {slot}</p>
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>
                            
                            <!-- QR Code Section -->
                            <tr>
                                <td align="center" style="padding: 10px 40px 30px 40px;">
                                    <h3 style="color: #1f2937; font-size: 18px; margin: 0 0 15px 0;">Your Entry QR Code</h3>
                                    <div style="background-color: #ffffff; padding: 15px; border: 2px dashed #cbd5e1; display: inline-block; border-radius: 8px;">
                                        <img src="https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={qr_code}" alt="QR Code" width="200" height="200" style="display: block; border: 0;" />
                                    </div>
                                    <p style="color: #64748b; font-size: 13px; margin: 15px 0 0 0;">
                                        Please present this QR code to the staff at the venue to check in.<br>
                                        If the image does not load, your manual entry code is: <strong>{qr_code}</strong>
                                    </p>
                                </td>
                            </tr>
                            
                            <!-- Footer -->
                            <tr>
                                <td align="center" style="padding: 20px; background-color: #f1f5f9; border-radius: 0 0 8px 8px; border-top: 1px solid #e2e8f0;">
                                    <p style="color: #94a3b8; font-size: 12px; margin: 0;">
                                        &copy; 2026 Campus Sports ERP. All rights reserved.<br>
                                        This is an automated message, please do not reply.
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_USERNAME
        msg["To"] = user_email
        msg.attach(MIMEText(html_body, "html"))
        
        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.sendmail(SMTP_USERNAME, user_email, msg.as_string())
            print(f"Successfully sent QR email to {user_email}")
        except Exception as e:
            print(f"Failed to send email to {user_email}: {e}")
            
    cursor.execute("SELECT email FROM users WHERE id = ?", (user_id,))
    u_email = cursor.fetchone()["email"]
    
    send_qr_email(u_email, booking_id, qr_code, fac["name"], data.booking_date, computed_time_slot)
    
    log_audit_event(
        action="EMAIL_SENT",
        status="SUCCESS",
        user_id=user_id,
        resource_type="booking",
        resource_id=booking_id,
        details=f"Sent Email to user with QR code for booking {booking_id}"
    )
    
    cursor.execute("""
        SELECT b.id, b.user_id, u.name as user_name, u.email as user_email,
               b.facility_id, f.name as facility_name,
               b.sport_id, s.name as sport_name,
               b.booking_date, b.time_slot, b.status, b.notes, b.idempotency_key, 
               b.qr_code, b.actual_entry_time, b.created_at
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
        details=f"Booking #{booking_id} created for facility '{fac['name']}' on {data.booking_date} ({computed_time_slot})"
    )
    
    return BookingResponse(**dict(row))

def list_user_bookings(user_id: int) -> List[BookingResponse]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.id, b.user_id, u.name as user_name, u.email as user_email,
               b.facility_id, f.name as facility_name,
               b.sport_id, s.name as sport_name,
               b.booking_date, b.time_slot, b.status, b.notes, b.idempotency_key, 
               b.qr_code, b.actual_entry_time, b.created_at
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
               b.booking_date, b.time_slot, b.status, b.notes, b.idempotency_key, 
               b.qr_code, b.actual_entry_time, b.created_at
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

def reschedule_booking(booking_id: int, user_id: int, data: BookingReschedule, is_admin: bool = False) -> BookingResponse:
    today_iso = date.today().isoformat()
    if data.new_booking_date < today_iso:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reschedule bookings to past dates."
        )

    computed_time_slot = f"{data.new_start_time} - {data.new_end_time}"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, user_id, facility_id, booking_date, time_slot, status 
        FROM bookings WHERE id = ?
    """, (booking_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")
    
    if not is_admin and row["user_id"] != user_id:
        conn.close()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only reschedule your own bookings.")
        
    if row["status"] != "confirmed":
        conn.close()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot reschedule a cancelled booking.")
        
    cursor.execute("SELECT open_time, close_time FROM facilities WHERE id = ?", (row["facility_id"],))
    fac = cursor.fetchone()
    if fac and (data.new_start_time < fac["open_time"] or data.new_end_time > fac["close_time"]):
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Requested slot {data.new_start_time} - {data.new_end_time} is outside facility operating hours ({fac['open_time']} - {fac['close_time']})."
        )
    if data.new_start_time >= data.new_end_time:
        conn.close()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Start time must be before end time.")

    # Check conflict excluding current booking_id (Overlap Logic)
    cursor.execute(
        "SELECT id, time_slot FROM bookings WHERE facility_id = ? AND booking_date = ? AND status = 'confirmed' AND id != ?",
        (row["facility_id"], data.new_booking_date, booking_id)
    )
    existing_bookings = cursor.fetchall()
    for eb in existing_bookings:
        try:
            eb_start, eb_end = eb["time_slot"].split(" - ")
            if data.new_start_time < eb_end and data.new_end_time > eb_start:
                conn.close()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail=f"Time slot overlaps with an existing booking: {eb['time_slot']}."
                )
        except ValueError:
            pass
        
    cursor.execute("""
        UPDATE bookings SET booking_date = ?, time_slot = ? WHERE id = ?
    """, (data.new_booking_date, computed_time_slot, booking_id))
    conn.commit()
    
    cursor.execute("""
        SELECT b.id, b.user_id, u.name as user_name, u.email as user_email,
               b.facility_id, f.name as facility_name,
               b.sport_id, s.name as sport_name,
               b.booking_date, b.time_slot, b.status, b.notes, b.idempotency_key,
               b.qr_code, b.actual_entry_time, b.created_at
        FROM bookings b
        LEFT JOIN users u ON b.user_id = u.id
        LEFT JOIN facilities f ON b.facility_id = f.id
        LEFT JOIN sports s ON b.sport_id = s.id
        WHERE b.id = ?
    """, (booking_id,))
    updated_row = cursor.fetchone()
    conn.close()
    
    log_audit_event(
        action="BOOKING_RESCHEDULED",
        user_id=user_id,
        resource_type="booking",
        resource_id=booking_id,
        details=f"Booking #{booking_id} rescheduled to {data.new_booking_date} ({computed_time_slot})"
    )
    
    return BookingResponse(**dict(updated_row))

def scan_qr_code(qr_code: str, admin_user_id: int) -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, status, booking_date, time_slot, user_id
        FROM bookings
        WHERE qr_code = ?
    """, (qr_code,))
    booking = cursor.fetchone()
    
    if not booking:
        conn.close()
        log_audit_event("QR_SCAN_FAILED", user_id=admin_user_id, details=f"Invalid QR Code scanned: {qr_code}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid QR Code")
        
    booking_id = booking["id"]
    if booking["status"] == "attended":
        conn.close()
        log_audit_event("QR_SCAN_FAILED", user_id=admin_user_id, resource_type="booking", resource_id=booking_id, details="QR Code already used")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="QR Code already used")
    elif booking["status"] == "cancelled":
        conn.close()
        log_audit_event("QR_SCAN_FAILED", user_id=admin_user_id, resource_type="booking", resource_id=booking_id, details="Attempt to scan cancelled booking")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking was cancelled")
        
    today_iso = date.today().isoformat()
    if booking["booking_date"] != today_iso:
        conn.close()
        log_audit_event("QR_SCAN_FAILED", user_id=admin_user_id, resource_type="booking", resource_id=booking_id, details=f"Invalid booking date ({booking['booking_date']} vs {today_iso})")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid booking date / Expired")
        
    cursor.execute("UPDATE bookings SET status = 'attended', actual_entry_time = CURRENT_TIMESTAMP WHERE id = ?", (booking_id,))
    
    # Mark Attendance automatically
    cursor.execute(
        "INSERT INTO attendance (booking_id, user_id, status, marked_by) VALUES (?, ?, ?, ?)",
        (booking_id, booking["user_id"], "present", admin_user_id)
    )
    conn.commit()
    
    cursor.execute("""
        SELECT b.id, b.user_id, u.name as user_name, u.email as user_email,
               b.facility_id, f.name as facility_name,
               b.sport_id, s.name as sport_name,
               b.booking_date, b.time_slot, b.status, b.notes, b.idempotency_key,
               b.qr_code, b.actual_entry_time, b.created_at
        FROM bookings b
        LEFT JOIN users u ON b.user_id = u.id
        LEFT JOIN facilities f ON b.facility_id = f.id
        LEFT JOIN sports s ON b.sport_id = s.id
        WHERE b.id = ?
    """, (booking_id,))
    updated_booking = cursor.fetchone()
    conn.close()
    
    log_audit_event("QR_SCAN_SUCCESS", user_id=admin_user_id, resource_type="booking", resource_id=booking_id, details="QR Code scanned successfully")
    
    return {
        "message": "Check-in successful",
        "booking": BookingResponse(**dict(updated_booking))
    }

def get_scan_history(booking_id: int) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, user_id, action, details, created_at
        FROM audit_logs
        WHERE resource_type = 'booking' AND resource_id = ? AND action LIKE 'QR_SCAN_%'
        ORDER BY created_at DESC
    """, (booking_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

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

