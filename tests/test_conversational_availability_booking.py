"""
tests/test_conversational_availability_booking.py
--------------------------------------------------
Automated regression tests for Admin/User conversational availability-to-booking flows:
1. availability -> Yes -> confirmation -> Yes -> booking
2. availability -> No -> action cancelled
3. availability -> unrelated query -> no booking
4. availability context isolation between users (Admin vs Student)
5. expired availability context (> 10 min TTL)
"""

import pytest
from datetime import datetime, timedelta, date
from app.query_agent import process_query, get_or_create_session, SESSION_STORE

def test_availability_to_booking_two_step_affirmation_flow(client, admin_token):
    """
    Test 1:
    Turn 1 (Availability): Admin asks "Check badminton availability on 2026-11-15 at 5 PM"
           -> Returns check_slot_availability, arms availability_followup.
    Turn 2 (First 'Yes'): Admin says "Yes"
           -> Returns confirm_booking_request (prompts final confirmation, does not book yet).
    Turn 3 (Final 'Yes'): Admin says "Yes"
           -> Returns booking_confirmed, creates booking record in DB.
    """
    admin_user = {"id": 1, "name": "Admin User", "email": "admin@sports.edu", "role": "admin"}
    session_id = "admin_avail_flow_seq_1"
    target_date = "2026-11-15"

    # Turn 1: Availability check
    q1 = process_query(f"Check badminton availability on {target_date} at 5 PM", admin_user, session_id=session_id)
    assert q1.intent == "check_slot_availability"
    assert q1.success is True
    assert "17:00 - 18:00" in q1.message
    session = get_or_create_session(session_id, 1)
    assert session["pending_action"] is not None
    assert session["pending_action"]["type"] == "availability_followup"
    assert session["pending_action"]["time_slot"] == "17:00 - 18:00"

    # Turn 2: First "Yes" -> Arms final confirmation
    q2 = process_query("Yes", admin_user, session_id=session_id)
    assert q2.intent == "confirm_booking_request"
    assert q2.pending_confirmation is True
    assert "Please confirm" in q2.message
    assert "17:00 - 18:00" in q2.message
    assert session["pending_action"]["type"] == "book_slot"

    # Turn 3: Second "Yes" -> Commits booking
    q3 = process_query("Yes", admin_user, session_id=session_id)
    assert q3.intent == "booking_confirmed"
    assert q3.success is True
    assert q3.action_taken == "create_booking"
    assert session["pending_action"] is None

def test_availability_cancellation_on_no():
    """
    Test 2:
    Turn 1: "Check badminton availability on 2026-11-16 at 5 PM"
    Turn 2: "No" -> Cancels pending action cleanly.
    """
    admin_user = {"id": 1, "name": "Admin User", "email": "admin@sports.edu", "role": "admin"}
    session_id = "admin_avail_cancel_seq"
    target_date = "2026-11-16"

    # Turn 1: Availability check
    q1 = process_query(f"Check badminton availability on {target_date} at 5 PM", admin_user, session_id=session_id)
    assert q1.intent == "check_slot_availability"
    session = get_or_create_session(session_id, 1)
    assert session["pending_action"] is not None

    # Turn 2: "No"
    q2 = process_query("No", admin_user, session_id=session_id)
    assert q2.intent == "action_cancelled"
    assert "cancelled" in q2.message.lower()
    assert session["pending_action"] is None

def test_availability_unrelated_interruption_no_booking():
    """
    Test 3:
    Turn 1: "Check badminton availability on 2026-11-17 at 5 PM"
    Turn 2: "Who am I?" -> Answers identity, clears pending action, creates NO booking.
    Turn 3: "Yes" -> No booking created.
    """
    admin_user = {"id": 1, "name": "Admin User", "email": "admin@sports.edu", "role": "admin"}
    session_id = "admin_avail_interrupt_seq"
    target_date = "2026-11-17"

    # Turn 1: Availability check
    q1 = process_query(f"Check badminton availability on {target_date} at 5 PM", admin_user, session_id=session_id)
    assert q1.intent == "check_slot_availability"
    session = get_or_create_session(session_id, 1)
    assert session["pending_action"] is not None

    # Turn 2: Unrelated query
    q2 = process_query("Who am I?", admin_user, session_id=session_id)
    assert q2.intent == "who_am_i"
    assert "Admin User" in q2.message
    assert session["pending_action"] is None

    # Turn 3: "Yes" (after interruption) -> Generic help, not booking
    q3 = process_query("Yes", admin_user, session_id=session_id)
    assert q3.intent != "booking_confirmed"
    assert q3.action_taken != "create_booking"

def test_availability_context_isolation_between_users():
    """
    Test 4:
    Admin checks availability in session A.
    Student in session B cannot confirm or access Admin's pending availability.
    """
    admin_user = {"id": 1, "name": "Admin User", "email": "admin@sports.edu", "role": "admin"}
    student_user = {"id": 2, "name": "Rahul Sharma", "email": "student@sports.edu", "role": "student"}
    session_id = "shared_sess_name"
    target_date = "2026-11-18"

    # Admin checks availability
    q_admin = process_query(f"Check badminton availability on {target_date} at 5 PM", admin_user, session_id=session_id)
    assert q_admin.intent == "check_slot_availability"
    
    # Student in their session says "Yes" without prior availability check
    q_student = process_query("Yes", student_user, session_id=session_id)
    assert q_student.intent != "booking_confirmed"
    assert q_student.intent != "confirm_booking_request"
    assert q_student.action_taken is None

def test_expired_availability_context():
    """
    Test 5:
    Availability context expires after 10-minute TTL.
    """
    admin_user = {"id": 1, "name": "Admin User", "email": "admin@sports.edu", "role": "admin"}
    session_id = "admin_avail_ttl_seq"
    target_date = "2026-11-19"

    # Turn 1: Availability check
    q1 = process_query(f"Check badminton availability on {target_date} at 5 PM", admin_user, session_id=session_id)
    assert q1.intent == "check_slot_availability"
    
    # Manually age the pending action beyond 10 minutes
    session = get_or_create_session(session_id, 1)
    session["pending_action"]["timestamp"] = datetime.now() - timedelta(minutes=15)

    # Turn 2: "Yes" on expired context
    q2 = process_query("Yes", admin_user, session_id=session_id)
    assert q2.intent == "pending_action_expired"
    assert "expired" in q2.message.lower()
    assert session["pending_action"] is None
