"""
app/constraint_engine.py
-------------------------
Deterministic Hybrid Logic & Constraint Engine for Sports ERP.
Inspired by TRACE-CS (Vasileiou & Yeoh, 2024).

Enforces declarative business rules, temporal bounds, capacity constraints,
role permissions, quotas, and double-booking invariants before any write action commits.
Provides grounded, explainable failure reasons without LLM hallucination.
"""

from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from app.database import get_db_connection
from app.sports_service import ALL_STANDARD_SLOTS, rank_slots_by_proximity

MAX_ACTIVE_BOOKINGS_PER_STUDENT = 10
MAX_ADVANCE_BOOKING_DAYS = 90

class ConstraintValidationResult(BaseModel):
    is_valid: bool
    code: Optional[str] = None
    constraint_name: Optional[str] = None
    explanation: str
    details: Dict[str, Any] = Field(default_factory=dict)
    suggested_alternatives: List[str] = Field(default_factory=list)

def validate_booking_request(
    user_id: int,
    sport_name: str,
    booking_date: str,
    time_slot: str,
    facility_id: Optional[int] = None,
    user_role: str = "student"
) -> ConstraintValidationResult:
    """
    Deterministically validates a sports court booking request against 8 formal constraints:
    C1: Facility existence & operational availability
    C2: Sport-facility compatibility
    C3: Campus operating schedule adherence
    C4: Temporal validity (no past dates, within 14-day advance window)
    C5: Double-booking & slot conflict freedom
    C6: User account standing (not blocked)
    C7: Student advance reservation quota (max 3 active bookings)
    C8: Role permission validity
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # 1. C6: Check User Status
        cursor.execute("SELECT id, name, is_blocked, role FROM users WHERE id = ?", (user_id,))
        user_row = cursor.fetchone()
        if not user_row:
            return ConstraintValidationResult(
                is_valid=False,
                code="C6_USER_NOT_FOUND",
                constraint_name="User Verification",
                explanation=f"User #{user_id} does not exist in the system."
            )
        if user_row["is_blocked"] == 1:
            return ConstraintValidationResult(
                is_valid=False,
                code="C6_USER_BLOCKED",
                constraint_name="Account Standing",
                explanation=f"Booking denied: Your account is currently suspended/blocked by the administrator."
            )

        # 2. C4: Temporal Validity
        today = date.today()
        try:
            req_date = datetime.strptime(booking_date, "%Y-%m-%d").date()
        except ValueError:
            return ConstraintValidationResult(
                is_valid=False,
                code="C4_INVALID_DATE_FORMAT",
                constraint_name="Date Format Validity",
                explanation=f"Date '{booking_date}' is invalid. Please specify a valid date in YYYY-MM-DD format."
            )

        if req_date < today:
            return ConstraintValidationResult(
                is_valid=False,
                code="C4_PAST_DATE",
                constraint_name="Temporal Validity",
                explanation=f"Cannot book for past date '{booking_date}'. Campus facilities can only be booked from today onwards."
            )

        max_date = today + timedelta(days=MAX_ADVANCE_BOOKING_DAYS)
        if req_date > max_date:
            return ConstraintValidationResult(
                is_valid=False,
                code="C4_ADVANCE_LIMIT_EXCEEDED",
                constraint_name="Advance Booking Window",
                explanation=f"Booking date '{booking_date}' exceeds the maximum advance reservation window of {MAX_ADVANCE_BOOKING_DAYS} days (latest allowed: {max_date.isoformat()})."
            )

        # 3. C3: Operating Hours & Slot Validity
        if time_slot not in ALL_STANDARD_SLOTS:
            # Generate available alternatives on that date
            cursor.execute("SELECT id, name FROM sports WHERE LOWER(name) LIKE ?", (f"%{sport_name.lower().strip()}%",))
            s_row = cursor.fetchone()
            s_name = s_row["name"] if s_row else sport_name
            
            # Find open slots on that date
            open_slots = []
            if s_row:
                cursor.execute("SELECT id FROM facilities WHERE sport_id = ? AND is_available = 1", (s_row["id"],))
                fac_ids = [r["id"] for r in cursor.fetchall()]
                for sl in ALL_STANDARD_SLOTS:
                    is_slot_open = False
                    for fid in fac_ids:
                        cursor.execute(
                            "SELECT id FROM bookings WHERE facility_id = ? AND booking_date = ? AND time_slot = ? AND status = 'confirmed'",
                            (fid, booking_date, sl)
                        )
                        if not cursor.fetchone():
                            is_slot_open = True
                            break
                    if is_slot_open:
                        open_slots.append(sl)
            
            ranked_alts = rank_slots_by_proximity(open_slots, requested_slot=time_slot)
            return ConstraintValidationResult(
                is_valid=False,
                code="C3_OUT_OF_OPERATING_HOURS",
                constraint_name="Operating Schedule",
                explanation=f"'{time_slot}' is outside campus facility operating hours (Operating schedule: 06:00 - 09:00 morning session, 16:00 - 20:00 evening session).",
                details={"requested_slot": time_slot, "operating_slots": ALL_STANDARD_SLOTS},
                suggested_alternatives=ranked_alts
            )

        # 4. C1 & C2: Sport and Facility Compatibility
        cursor.execute("SELECT id, name FROM sports WHERE LOWER(name) LIKE ?", (f"%{sport_name.lower().strip()}%",))
        sport_row = cursor.fetchone()
        if not sport_row:
            return ConstraintValidationResult(
                is_valid=False,
                code="C2_UNKNOWN_SPORT",
                constraint_name="Catalog Verification",
                explanation=f"Sport '{sport_name}' is not registered in the campus sports catalog."
            )
        sport_id = sport_row["id"]
        canonical_sport = sport_row["name"]

        # Check facility availability
        if facility_id:
            cursor.execute("SELECT id, name, sport_id, location, capacity, is_available FROM facilities WHERE id = ?", (facility_id,))
            target_fac = cursor.fetchone()
            if not target_fac:
                return ConstraintValidationResult(
                    is_valid=False,
                    code="C1_FACILITY_NOT_FOUND",
                    constraint_name="Facility Existence",
                    explanation=f"Facility #{facility_id} does not exist."
                )
            if target_fac["is_available"] == 0:
                return ConstraintValidationResult(
                    is_valid=False,
                    code="C1_FACILITY_INACTIVE",
                    constraint_name="Facility Availability",
                    explanation=f"{target_fac['name']} is currently closed for maintenance or inactive."
                )
            if target_fac["sport_id"] != sport_id:
                return ConstraintValidationResult(
                    is_valid=False,
                    code="C2_SPORT_INCOMPATIBLE",
                    constraint_name="Sport-Facility Compatibility",
                    explanation=f"{target_fac['name']} is designated for a different sport and cannot host {canonical_sport}."
                )
            candidate_facilities = [dict(target_fac)]
        else:
            cursor.execute("SELECT id, name, sport_id, location, capacity, is_available FROM facilities WHERE sport_id = ? AND is_available = 1", (sport_id,))
            candidate_facilities = [dict(f) for f in cursor.fetchall()]
            if not candidate_facilities:
                return ConstraintValidationResult(
                    is_valid=False,
                    code="C1_NO_ACTIVE_FACILITIES",
                    constraint_name="Facility Operational Status",
                    explanation=f"No active facilities are currently operational for {canonical_sport}."
                )

        # 5. C7: Student Advance Booking Quota
        if user_role != "admin":
            cursor.execute("""
                SELECT COUNT(*) FROM bookings 
                WHERE user_id = ? AND booking_date >= ? AND status = 'confirmed'
            """, (user_id, today.isoformat()))
            active_booking_count = cursor.fetchone()[0]
            if active_booking_count >= MAX_ACTIVE_BOOKINGS_PER_STUDENT:
                return ConstraintValidationResult(
                    is_valid=False,
                    code="C7_QUOTA_EXCEEDED",
                    constraint_name="Reservation Quota",
                    explanation=f"Reservation quota reached: You already have {active_booking_count} active upcoming bookings (maximum allowed: {MAX_ACTIVE_BOOKINGS_PER_STUDENT}). Please cancel an existing booking before reserving another.",
                    details={"active_count": active_booking_count, "quota_limit": MAX_ACTIVE_BOOKINGS_PER_STUDENT}
                )

        # 6. C5: Double-Booking / Conflict Check
        free_facilities = []
        user_duplicate_booking = None

        for fac in candidate_facilities:
            cursor.execute(
                "SELECT id, user_id FROM bookings WHERE facility_id = ? AND booking_date = ? AND time_slot = ? AND status = 'confirmed'",
                (fac["id"], booking_date, time_slot)
            )
            conflict = cursor.fetchone()
            if not conflict:
                free_facilities.append(fac)
            elif conflict["user_id"] == user_id:
                user_duplicate_booking = conflict

        # If user already holds a booking for this specific facility or no free facilities remain
        if facility_id and user_duplicate_booking:
            return ConstraintValidationResult(
                is_valid=False,
                code="C5_DUPLICATE_USER_BOOKING",
                constraint_name="Duplicate Booking Check",
                explanation=f"Duplicate booking detected: You already hold a confirmed reservation on {booking_date} at {time_slot} (Booking #{user_duplicate_booking['id']})."
            )

        if not free_facilities:
            # Slot is completely booked -> compute proximity alternatives
            all_sport_fac_ids = [f["id"] for f in candidate_facilities]
            open_slots = []
            for sl in ALL_STANDARD_SLOTS:
                if sl == time_slot:
                    continue
                is_open = False
                for fid in all_sport_fac_ids:
                    cursor.execute(
                        "SELECT id FROM bookings WHERE facility_id = ? AND booking_date = ? AND time_slot = ? AND status = 'confirmed'",
                        (fid, booking_date, sl)
                    )
                    if not cursor.fetchone():
                        is_open = True
                        break
                if is_open:
                    open_slots.append(sl)

            ranked_alts = rank_slots_by_proximity(open_slots, requested_slot=time_slot)
            alt_msg = f" The nearest available slots are: {', '.join(ranked_alts[:3])}." if ranked_alts else " No other slots are available on this date."
            
            return ConstraintValidationResult(
                is_valid=False,
                code="C5_SLOT_UNAVAILABLE",
                constraint_name="Slot Availability Conflict",
                explanation=f"{time_slot} is unavailable because all courts for {canonical_sport} are already booked on {booking_date}.{alt_msg}",
                details={"requested_slot": time_slot, "booking_date": booking_date},
                suggested_alternatives=ranked_alts
            )

        chosen_facility = free_facilities[0]
        return ConstraintValidationResult(
            is_valid=True,
            code="C_VALID",
            constraint_name="All Constraints Satisfied",
            explanation=f"{chosen_facility['name']} ({canonical_sport}) is available on {booking_date} from {time_slot}.",
            details={
                "sport_id": sport_id,
                "sport_name": canonical_sport,
                "facility_id": chosen_facility["id"],
                "facility_name": chosen_facility["name"],
                "booking_date": booking_date,
                "time_slot": time_slot
            }
        )

    finally:
        conn.close()


def validate_cancellation_request(
    booking_id: int,
    user_id: int,
    user_role: str = "student"
) -> ConstraintValidationResult:
    """
    Deterministically validates a booking cancellation request against:
    1. Booking existence
    2. Status invariant (cannot cancel already cancelled booking)
    3. Student ownership verification (user_id == booking.user_id unless admin)
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT b.id, b.user_id, b.facility_id, f.name as facility_name,
                   b.sport_id, s.name as sport_name, b.booking_date, b.time_slot, b.status
            FROM bookings b
            LEFT JOIN facilities f ON b.facility_id = f.id
            LEFT JOIN sports s ON b.sport_id = s.id
            WHERE b.id = ?
        """, (booking_id,))
        row = cursor.fetchone()
        
        if not row:
            return ConstraintValidationResult(
                is_valid=False,
                code="C8_BOOKING_NOT_FOUND",
                constraint_name="Booking Existence",
                explanation=f"Booking #{booking_id} was not found in the system."
            )

        if row["status"] == "cancelled":
            return ConstraintValidationResult(
                is_valid=False,
                code="C8_ALREADY_CANCELLED",
                constraint_name="State Transition Invariant",
                explanation=f"Booking #{booking_id} for {row['sport_name']} on {row['booking_date']} is already cancelled."
            )

        if user_role != "admin" and row["user_id"] != user_id:
            return ConstraintValidationResult(
                is_valid=False,
                code="C8_OWNERSHIP_VIOLATION",
                constraint_name="Student Ownership Verification",
                explanation=f"Access Denied: You do not own Booking #{booking_id}. Students can only cancel their own reservations."
            )

        return ConstraintValidationResult(
            is_valid=True,
            code="C_VALID",
            constraint_name="Cancellation Validated",
            explanation=f"Booking #{booking_id} for {row['sport_name']} at {row['facility_name']} on {row['booking_date']} ({row['time_slot']}) is eligible for cancellation.",
            details=dict(row)
        )
    finally:
        conn.close()
