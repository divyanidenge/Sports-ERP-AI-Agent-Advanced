import sqlite3
from datetime import date, datetime
from typing import Dict, Any, List, Optional
from app.database import get_db_connection
import app.sports_service as sports_service
import app.auth_service as auth_service
from app.models import BookingCreate

ALL_STANDARD_SLOTS = [
    "06:00 - 07:00",
    "07:00 - 08:00",
    "08:00 - 09:00",
    "16:00 - 17:00",
    "17:00 - 18:00",
    "18:00 - 19:00",
    "19:00 - 20:00"
]

def search_my_bookings(user_id: int, filter_type: str = "all") -> Dict[str, Any]:
    """Retrieves bookings strictly for the authenticated student with optional filtering (all, active, today, upcoming, cancelled, next)."""
    bookings = sports_service.list_user_bookings(user_id)
    data = [b.model_dump() for b in bookings]
    today_str = date.today().isoformat()
    
    if not data:
        return {
            "success": True,
            "count": 0,
            "active_count": 0,
            "message": "You currently have no bookings on record.",
            "data": []
        }
    
    filtered_data = data
    msg_prefix = ""
    
    if filter_type == "today":
        filtered_data = [b for b in data if b["booking_date"] == today_str and b["status"] == "confirmed"]
        msg_prefix = "today's active"
    elif filter_type == "upcoming":
        filtered_data = [b for b in data if b["booking_date"] >= today_str and b["status"] == "confirmed"]
        msg_prefix = "upcoming confirmed"
    elif filter_type == "cancelled":
        filtered_data = [b for b in data if b["status"] == "cancelled"]
        msg_prefix = "cancelled"
    elif filter_type == "next":
        upcoming = [b for b in data if b["booking_date"] >= today_str and b["status"] == "confirmed"]
        upcoming.sort(key=lambda x: (x["booking_date"], x["time_slot"]))
        if upcoming:
            next_b = upcoming[0]
            return {
                "success": True,
                "count": 1,
                "active_count": len(upcoming),
                "message": f"Your next booking is for {next_b['sport_name']} at {next_b['facility_name']} on {next_b['booking_date']} ({next_b['time_slot']}).",
                "data": [next_b]
            }
        else:
            return {
                "success": True,
                "count": 0,
                "active_count": 0,
                "message": "You have no upcoming bookings scheduled.",
                "data": []
            }
    elif filter_type == "active":
        filtered_data = [b for b in data if b["status"] == "confirmed"]
        msg_prefix = "active confirmed"
    else:
        filtered_data = data
        msg_prefix = "total"

    active_count = len([b for b in data if b["status"] == "confirmed"])
    count = len(filtered_data)
    
    if count == 0:
        return {
            "success": True,
            "count": 0,
            "active_count": active_count,
            "message": f"You have no {msg_prefix} bookings on record.",
            "data": []
        }
    
    return {
        "success": True,
        "count": count,
        "active_count": active_count,
        "message": f"Found {count} {msg_prefix} booking(s) for your account.",
        "data": filtered_data
    }

def get_user_attendance_tool(user_id: int, sport_name: str = "") -> Dict[str, Any]:
    """Retrieves attendance history and statistics for the logged-in student."""
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
        SELECT a.id, a.booking_id, a.check_in_time, a.status,
               b.booking_date, b.time_slot, f.name as facility_name, s.name as sport_name
        FROM attendance a
        LEFT JOIN bookings b ON a.booking_id = b.id
        LEFT JOIN facilities f ON b.facility_id = f.id
        LEFT JOIN sports s ON b.sport_id = s.id
        WHERE a.user_id = ?
    """
    params = [user_id]
    if sport_name:
        query += " AND LOWER(s.name) LIKE ?"
        params.append(f"%{sport_name.lower().strip()}%")
    query += " ORDER BY a.check_in_time DESC"
    
    cursor.execute(query, tuple(params))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    total_sessions = len(rows)
    present_count = len([r for r in rows if r["status"] == "present"])
    absent_count = len([r for r in rows if r["status"] == "absent"])
    late_count = len([r for r in rows if r["status"] == "late"])
    
    rate = round((present_count / total_sessions * 100) if total_sessions > 0 else 0.0, 1)
    
    if total_sessions == 0:
        msg = f"You have no attendance records logged yet{' for ' + sport_name if sport_name else ''}. Your attendance rate is 0.0% across 0 sessions."
    else:
        msg = (
            f"Attendance Summary{' for ' + sport_name if sport_name else ''}: "
            f"{present_count} attended (present) out of {total_sessions} session(s) "
            f"({rate}% attendance rate). Missed/Absent: {absent_count}."
        )

    return {
        "success": True,
        "count": total_sessions,
        "present_count": present_count,
        "absent_count": absent_count,
        "late_count": late_count,
        "attendance_rate": rate,
        "message": msg,
        "data": rows
    }

def check_availability(sport_name: str, booking_date: str, time_slot: str) -> Dict[str, Any]:
    """Checks if a facility is available for a given sport, date, and time slot."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Find matching sports
    cursor.execute("SELECT id, name FROM sports WHERE LOWER(name) LIKE ?", (f"%{sport_name.lower().strip()}%",))
    sport_row = cursor.fetchone()
    if not sport_row:
        conn.close()
        return {
            "success": False,
            "available": False,
            "message": f"Sport '{sport_name}' is not currently registered in the campus catalog.",
            "data": None
        }
    
    sport_id = sport_row["id"]
    matched_sport_name = sport_row["name"]

    # Find facilities for this sport
    cursor.execute("SELECT id, name, location, capacity FROM facilities WHERE sport_id = ? AND is_available = 1", (sport_id,))
    facilities = [dict(f) for f in cursor.fetchall()]
    if not facilities:
        conn.close()
        return {
            "success": False,
            "available": False,
            "message": f"No active facilities are currently available for {matched_sport_name}.",
            "data": None
        }

    # Check if requested slot is part of campus operating slots
    if time_slot not in ALL_STANDARD_SLOTS:
        conn.close()
        alt = find_alternative_slots(matched_sport_name, booking_date, time_slot)
        return {
            "success": True,
            "available": False,
            "sport_id": sport_id,
            "sport_name": matched_sport_name,
            "booking_date": booking_date,
            "time_slot": time_slot,
            "message": f"{matched_sport_name} is unavailable at {time_slot} on {booking_date}.",
            "alternative_slots": alt.get("available_slots", [])
        }

    # Find free facility
    available_facilities = []
    for fac in facilities:
        cursor.execute(
            "SELECT id FROM bookings WHERE facility_id = ? AND booking_date = ? AND time_slot = ? AND status = 'confirmed'",
            (fac["id"], booking_date, time_slot)
        )
        if not cursor.fetchone():
            available_facilities.append(fac)
    
    conn.close()

    if available_facilities:
        chosen = available_facilities[0]
        return {
            "success": True,
            "available": True,
            "sport_id": sport_id,
            "sport_name": matched_sport_name,
            "facility_id": chosen["id"],
            "facility_name": chosen["name"],
            "location": chosen["location"],
            "booking_date": booking_date,
            "time_slot": time_slot,
            "message": f"{chosen['name']} ({matched_sport_name}) is available on {booking_date} at {time_slot}."
        }
    else:
        # Search for alternatives
        alt = find_alternative_slots(matched_sport_name, booking_date, time_slot)
        return {
            "success": True,
            "available": False,
            "sport_id": sport_id,
            "sport_name": matched_sport_name,
            "booking_date": booking_date,
            "time_slot": time_slot,
            "message": f"{matched_sport_name} is already booked on {booking_date} at {time_slot}.",
            "alternative_slots": alt.get("available_slots", [])
        }

def find_alternative_slots(sport_name: str, booking_date: str, requested_slot: Optional[str] = None) -> Dict[str, Any]:
    """Finds all available time slots for a given sport on a specific date, ranked by proximity to requested time."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, name FROM sports WHERE LOWER(name) LIKE ?", (f"%{sport_name.lower().strip()}%",))
    sport_row = cursor.fetchone()
    if not sport_row:
        conn.close()
        return {"success": False, "available_slots": [], "message": f"Sport '{sport_name}' not found."}

    sport_id = sport_row["id"]
    cursor.execute("SELECT id, name FROM facilities WHERE sport_id = ? AND is_available = 1", (sport_id,))
    facilities = [dict(f) for f in cursor.fetchall()]
    if not facilities:
        conn.close()
        return {"success": False, "available_slots": [], "message": f"No active facilities for {sport_row['name']}."}

    free_slots = []
    slot_capacities = {}
    for slot in ALL_STANDARD_SLOTS:
        if requested_slot and slot == requested_slot:
            continue
        # Count free facilities for this slot
        free_count = 0
        for fac in facilities:
            cursor.execute(
                "SELECT id FROM bookings WHERE facility_id = ? AND booking_date = ? AND time_slot = ? AND status = 'confirmed'",
                (fac["id"], booking_date, slot)
            )
            if not cursor.fetchone():
                free_count += 1
        
        if free_count > 0:
            free_slots.append(slot)
            slot_capacities[slot] = free_count

    conn.close()
    
    # Rank available slots: closest to requested hour first, then higher capacity, then chronological
    ranked_slots = sports_service.rank_slots_by_proximity(free_slots, requested_slot=requested_slot, slot_capacities=slot_capacities)
    
    return {
        "success": True,
        "sport_name": sport_row["name"],
        "booking_date": booking_date,
        "available_slots": ranked_slots,
        "message": f"Available slots for {sport_row['name']} on {booking_date}: {', '.join(ranked_slots) if ranked_slots else 'None'}"
    }

def create_booking_tool(user_id: int, sport_name: str, booking_date: str, time_slot: str, notes: str = "", idempotency_key: Optional[str] = None) -> Dict[str, Any]:
    """Creates a booking after checking availability."""
    avail = check_availability(sport_name, booking_date, time_slot)
    if not avail["success"] or not avail["available"]:
        alt_slots = avail.get("alternative_slots", [])
        if alt_slots:
            slot_str = ", ".join(alt_slots[:3])
            return {
                "success": False,
                "message": f"{sport_name} is already booked at {time_slot} on {booking_date}. I found these alternative slots available: {slot_str}. Which one would you prefer?",
                "alternative_slots": alt_slots
            }
        return {
            "success": False,
            "message": avail.get("message", f"Cannot book {sport_name} at {time_slot} on {booking_date}."),
            "alternative_slots": []
        }

    fac_id = avail["facility_id"]
    sport_id = avail["sport_id"]
    if not idempotency_key:
        clean_slot = time_slot.replace(" ", "").replace(":", "")
        idempotency_key = f"ai-book-{user_id}-{fac_id}-{booking_date}-{clean_slot}"

    booking_req = BookingCreate(
        facility_id=fac_id,
        sport_id=sport_id,
        booking_date=booking_date,
        time_slot=time_slot,
        notes=notes or "Booked via AI Assistant",
        idempotency_key=idempotency_key
    )
    try:
        created = sports_service.create_booking(user_id, booking_req)
        return {
            "success": True,
            "message": f"Done! {avail['facility_name']} ({avail['sport_name']}) has been booked for you on {booking_date} at {time_slot}.",
            "data": created.model_dump()
        }
    except Exception as e:
        detail = getattr(e, "detail", str(e))
        return {
            "success": False,
            "message": f"Booking failed: {detail}",
            "data": None
        }

def cancel_booking_tool(user_id: int, role: str, sport_name: str = "", booking_id: int = 0, booking_date: str = "", time_slot: str = "", target_type: str = "latest") -> Dict[str, Any]:
    """Cancels a booking by ID or by matching the user's booking for a sport, date, or time slot."""
    conn = get_db_connection()
    cursor = conn.cursor()

    target_booking = None
    if booking_id > 0:
        cursor.execute("SELECT id, user_id, status FROM bookings WHERE id = ?", (booking_id,))
        target_booking = cursor.fetchone()
        if target_booking and role != "admin" and target_booking["user_id"] != user_id:
            conn.close()
            return {
                "success": False,
                "message": "Access Denied: You can only cancel your own bookings."
            }
    else:
        query = """
            SELECT b.id, b.user_id, b.status, s.name as sport_name, b.booking_date, b.time_slot
            FROM bookings b
            LEFT JOIN sports s ON b.sport_id = s.id
            WHERE b.status = 'confirmed'
        """
        params = []
        if role != "admin":
            query += " AND b.user_id = ?"
            params.append(user_id)
        if sport_name:
            query += " AND LOWER(s.name) LIKE ?"
            params.append(f"%{sport_name.lower().strip()}%")
        if booking_date:
            query += " AND b.booking_date = ?"
            params.append(booking_date)
        if time_slot:
            query += " AND b.time_slot = ?"
            params.append(time_slot)
        
        if target_type == "next":
            today_str = date.today().isoformat()
            query += " AND b.booking_date >= ? ORDER BY b.booking_date ASC, b.time_slot ASC LIMIT 1"
            params.append(today_str)
        else:
            query += " ORDER BY b.id DESC LIMIT 1"

        cursor.execute(query, tuple(params))
        target_booking = cursor.fetchone()
    
    conn.close()

    if not target_booking:
        return {
            "success": False,
            "message": f"No active confirmed booking found to cancel{' for ' + sport_name if sport_name else ''}."
        }
    
    b_id = target_booking["id"]
    is_admin = (role == "admin")
    try:
        res = sports_service.cancel_booking(b_id, user_id, is_admin=is_admin)
        return {
            "success": True,
            "message": f"Booking #{b_id} has been cancelled successfully.",
            "data": res
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Cancellation error: {getattr(e, 'detail', str(e))}"
        }

def restore_booking_tool(user_id: int, role: str, booking_id: int) -> Dict[str, Any]:
    """Restores a previously cancelled booking after validating ownership, availability, constraints, and audit logging."""
    if not booking_id or booking_id <= 0:
        return {
            "success": False,
            "message": "Please specify the booking ID you would like to restore (e.g. 'Restore booking 41')."
        }
    is_admin = (role == "admin")
    try:
        res = sports_service.restore_booking(booking_id=booking_id, user_id=user_id, is_admin=is_admin)
        return {
            "success": True,
            "message": res["message"],
            "data": res
        }
    except Exception as e:
        detail = getattr(e, "detail", str(e))
        return {
            "success": False,
            "message": f"Restore failed: {detail}",
            "data": None
        }

def list_sports_tool() -> Dict[str, Any]:
    """Lists all sports disciplines."""
    sports = sports_service.list_sports()
    data = [s.model_dump() for s in sports]
    return {
        "success": True,
        "count": len(data),
        "message": f"We offer {len(data)} sports on campus: {', '.join([s['name'] for s in data])}.",
        "data": data
    }

def list_facilities_tool(sport_name: str = "") -> Dict[str, Any]:
    """Lists all campus sports facilities, optionally filtered by sport."""
    facs = sports_service.list_facilities()
    data = [f.model_dump() for f in facs]
    if sport_name:
        data = [f for f in data if sport_name.lower() in (f.get("sport_name") or "").lower()]
    return {
        "success": True,
        "count": len(data),
        "message": f"Found {len(data)} sports facilities/courts.",
        "data": data
    }

def get_dashboard_stats_tool() -> Dict[str, Any]:
    """Retrieves overall campus sports statistics."""
    stats = sports_service.get_dashboard_overview()
    dump = stats.model_dump()
    return {
        "success": True,
        "message": f"Sports ERP Overview: {dump['total_users']} registered users ({dump['active_students']} active students), {dump['total_sports']} sports, {dump['total_facilities']} facilities, and {dump['total_bookings']} total bookings.",
        "data": dump
    }

def list_all_users_tool(role: str) -> Dict[str, Any]:
    """Admin tool: lists all registered users."""
    if role != "admin":
        return {
            "success": False,
            "message": "Access Denied: Only administrators can view the user directory.",
            "data": None
        }
    users = auth_service.list_all_users()
    data = [u.model_dump() for u in users]
    return {
        "success": True,
        "count": len(data),
        "message": f"Retrieved {len(data)} registered users from the system.",
        "data": data
    }

def block_user_tool(role: str, user_identifier: str) -> Dict[str, Any]:
    """Admin tool: blocks a user by user ID or name."""
    if role != "admin":
        return {
            "success": False,
            "message": "Permission Denied: Only administrators can block users.",
            "data": None
        }
    
    conn = get_db_connection()
    cursor = conn.cursor()
    target_user = None

    # Check if integer ID
    if user_identifier.isdigit():
        cursor.execute("SELECT id, name, email, role, is_blocked FROM users WHERE id = ?", (int(user_identifier),))
        target_user = cursor.fetchone()
    else:
        cursor.execute(
            "SELECT id, name, email, role, is_blocked FROM users WHERE LOWER(name) LIKE ? OR LOWER(email) LIKE ?",
            (f"%{user_identifier.lower().strip()}%", f"%{user_identifier.lower().strip()}%")
        )
        target_user = cursor.fetchone()
    
    conn.close()

    if not target_user:
        return {
            "success": False,
            "message": f"User '{user_identifier}' was not found in the database."
        }
    
    t_dict = dict(target_user)
    if t_dict["role"] == "admin":
        return {
            "success": False,
            "message": "Cannot block an administrator account."
        }
    if t_dict["is_blocked"] == 1:
        return {
            "success": True,
            "message": f"User '{t_dict['name']}' (ID #{t_dict['id']}) is already blocked."
        }

    try:
        res = auth_service.block_user_by_id(t_dict["id"])
        return {
            "success": True,
            "message": f"User '{t_dict['name']}' (ID #{t_dict['id']}) has been blocked successfully.",
            "data": res
        }
    except Exception as e:
        return {"success": False, "message": f"Failed to block user: {getattr(e, 'detail', str(e))}"}

def unblock_user_tool(role: str, user_identifier: str) -> Dict[str, Any]:
    """Admin tool: unblocks a user by user ID or name."""
    if role != "admin":
        return {
            "success": False,
            "message": "Permission Denied: Only administrators can unblock users.",
            "data": None
        }
    
    conn = get_db_connection()
    cursor = conn.cursor()
    target_user = None

    if user_identifier.isdigit():
        cursor.execute("SELECT id, name, email, role, is_blocked FROM users WHERE id = ?", (int(user_identifier),))
        target_user = cursor.fetchone()
    else:
        cursor.execute(
            "SELECT id, name, email, role, is_blocked FROM users WHERE LOWER(name) LIKE ? OR LOWER(email) LIKE ?",
            (f"%{user_identifier.lower().strip()}%", f"%{user_identifier.lower().strip()}%")
        )
        target_user = cursor.fetchone()
    
    conn.close()

    if not target_user:
        return {
            "success": False,
            "message": f"User '{user_identifier}' was not found in the database."
        }
    
    t_dict = dict(target_user)
    try:
        res = auth_service.unblock_user_by_id(t_dict["id"])
        return {
            "success": True,
            "message": f"User '{t_dict['name']}' (ID #{t_dict['id']}) has been unblocked successfully.",
            "data": res
        }
    except Exception as e:
        return {"success": False, "message": f"Failed to unblock user: {getattr(e, 'detail', str(e))}"}

def get_all_bookings_tool(role: str, filter_date: Optional[str] = None) -> Dict[str, Any]:
    """Admin tool: retrieves all campus bookings, optionally filtered by date."""
    if role != "admin":
        return {
            "success": False,
            "message": "Permission Denied: Only administrators can view all campus bookings.",
            "data": None
        }
    all_b = sports_service.list_all_bookings()
    data = [b.model_dump() for b in all_b]
    if filter_date:
        data = [b for b in data if b["booking_date"] == filter_date]
        msg = f"Retrieved {len(data)} booking(s) for {filter_date} across the campus."
    else:
        msg = f"Retrieved {len(data)} total campus booking(s)."
    return {
        "success": True,
        "count": len(data),
        "message": msg,
        "data": data
    }

def list_filtered_users_tool(role: str, user_filter: str = "all") -> Dict[str, Any]:
    """Admin tool: lists users filtered by role or blocked status ('all', 'blocked', 'student', 'admin')."""
    if role != "admin":
        return {
            "success": False,
            "message": "Permission Denied: Only administrators can view user records.",
            "data": None
        }
    users = auth_service.list_all_users()
    data = [u.model_dump() for u in users]
    
    if user_filter == "blocked":
        data = [u for u in data if u["is_blocked"] == 1]
        msg = f"Found {len(data)} blocked user(s)."
    elif user_filter == "student":
        data = [u for u in data if u["role"] == "student"]
        msg = f"Found {len(data)} registered student(s)."
    elif user_filter == "admin":
        data = [u for u in data if u["role"] == "admin"]
        msg = f"Found {len(data)} administrator account(s)."
    else:
        msg = f"Retrieved {len(data)} registered user(s)."

    return {
        "success": True,
        "count": len(data),
        "message": msg,
        "data": data
    }

def get_facility_utilization_tool() -> Dict[str, Any]:
    """Retrieves facility utilization metrics and individual court breakdown."""
    analytics = sports_service.get_advanced_analytics()
    breakdown = analytics.facility_breakdown
    msg = (
        f"🏟️ **Facility Utilization Analytics**:\n"
        f"• **Overall Facility Utilization Rate:** {analytics.facility_utilization_rate}%\n"
        f"• **Monitored Facilities:** {len(breakdown)} active campus facilities\n"
        f"• Check the breakdown below for individual court and ground utilization."
    )
    return {
        "success": True,
        "message": msg,
        "data": breakdown,
        "facility_utilization_rate": analytics.facility_utilization_rate
    }

def get_peak_booking_hours_tool() -> Dict[str, Any]:
    """Retrieves peak booking hours and time slot distribution."""
    analytics = sports_service.get_advanced_analytics()
    peak_dist = analytics.peak_hours_distribution
    top_slot = peak_dist[0]["time_slot"] if peak_dist else "None"
    msg = (
        f"⏰ **Peak Booking Hours Analytics**:\n"
        f"• **Busiest Time Slot:** {top_slot}\n"
        f"• **Active Peak Distribution:** Analyzed across all {len(ALL_STANDARD_SLOTS)} daily campus intervals.\n"
        f"• Check the table below for booking volumes per time slot."
    )
    return {
        "success": True,
        "message": msg,
        "data": peak_dist,
        "peak_slot": top_slot
    }

def get_sport_popularity_tool() -> Dict[str, Any]:
    """Retrieves sport popularity rankings and total reservations."""
    analytics = sports_service.get_advanced_analytics()
    pop_sports = analytics.popular_sports
    top_sport = pop_sports[0]["sport_name"] if pop_sports else "None"
    msg = (
        f"🏅 **Sport Popularity Analytics**:\n"
        f"• **#1 Most Popular Sport:** {top_sport}\n"
        f"• **Total Tracked Sports:** {len(pop_sports)} sports\n"
        f"• Check the breakdown below for popularity percentage and total reservations."
    )
    return {
        "success": True,
        "message": msg,
        "data": pop_sports,
        "top_sport": top_sport
    }

def get_cancellation_statistics_tool(user_id: Optional[int] = None, role: str = "admin") -> Dict[str, Any]:
    """Retrieves booking cancellation metrics."""
    analytics = sports_service.get_advanced_analytics()
    if role != "admin" and user_id is not None:
        user_bookings = sports_service.list_user_bookings(user_id)
        user_total = len(user_bookings)
        user_cancelled = len([b for b in user_bookings if b.status == "cancelled"])
        user_rate = round((user_cancelled / user_total * 100) if user_total > 0 else 0.0, 1)
        msg = (
            f"📋 **Your Personal Cancellation Summary**:\n"
            f"• **Total Bookings:** {user_total}\n"
            f"• **Cancelled Bookings:** {user_cancelled}\n"
            f"• **Personal Cancellation Rate:** {user_rate}%"
        )
        return {
            "success": True,
            "message": msg,
            "data": {
                "total_bookings": user_total,
                "cancelled_bookings": user_cancelled,
                "cancellation_rate": user_rate
            }
        }
    
    msg = (
        f"📊 **Campus Cancellation Statistics**:\n"
        f"• **Total Bookings Recorded:** {analytics.total_bookings}\n"
        f"• **Active Confirmed:** {analytics.active_confirmed_bookings}\n"
        f"• **Total Cancelled:** {analytics.cancelled_bookings}\n"
        f"• **Overall Cancellation Rate:** {analytics.cancellation_rate}%"
    )
    return {
        "success": True,
        "message": msg,
        "data": {
            "total_bookings": analytics.total_bookings,
            "active_confirmed_bookings": analytics.active_confirmed_bookings,
            "cancelled_bookings": analytics.cancelled_bookings,
            "cancellation_rate": analytics.cancellation_rate
        }
    }
