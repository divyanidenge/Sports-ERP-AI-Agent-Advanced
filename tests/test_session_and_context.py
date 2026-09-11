import pytest
from datetime import datetime, timedelta
import app.query_agent as qa
from app.query_agent import process_query, get_or_create_session

def test_multiturn_context_inheritance_and_booking():
    """
    Test:
    Turn 1: "What badminton slots are available tomorrow?" -> sets sport=Badminton and date=tomorrow in last_entities.
    Turn 2: "Book 08:00 - 09:00" -> inherits Badminton and tomorrow, arms pending_action.
    Turn 3: "Yes" -> commits booking and clears pending_action.
    """
    session_id = "test_multiturn_seq_1"
    student_user = {"id": 2, "name": "Rahul Sharma", "email": "student@sports.edu", "role": "student"}

    # Turn 1
    resp1 = process_query("What badminton slots are available tomorrow?", student_user, session_id=session_id)
    assert resp1.intent == "check_available_slots"
    session = get_or_create_session(session_id, 2)
    assert session["last_entities"]["sport"] == "Badminton"

    # Turn 2
    resp2 = process_query("Book 06:00 - 07:00", student_user, session_id=session_id)
    assert resp2.pending_confirmation is True
    assert "06:00 - 07:00" in resp2.message
    assert session["pending_action"] is not None

    # Turn 3
    resp3 = process_query("Yes", student_user, session_id=session_id)
    assert resp3.intent == "booking_confirmed"
    assert resp3.action_taken == "create_booking"
    assert session["pending_action"] is None

    # Clean up test booking to maintain daily quota headroom across test suite
    if resp3.data and "id" in resp3.data:
        from app.database import get_db_connection
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM bookings WHERE id = ?", (resp3.data["id"],))
        conn.commit()
        conn.close()

def test_confirmation_cancellation_on_no():
    """Verify that saying 'No' cleanly cancels the pending action."""
    session_id = "test_cancel_action_seq"
    student_user = {"id": 2, "name": "Rahul Sharma", "email": "student@sports.edu", "role": "student"}

    # Arm a booking
    resp1 = process_query("Book football tomorrow at 5 PM", student_user, session_id=session_id)
    assert resp1.pending_confirmation is True

    # Say No
    resp2 = process_query("No", student_user, session_id=session_id)
    assert resp2.intent == "action_cancelled"
    assert "cancelled" in resp2.message.lower()
    session = get_or_create_session(session_id, 2)
    assert session["pending_action"] is None

def test_unrelated_interruption_does_not_execute_pending_action():
    """Verify that an interrupted question (e.g. 'Who am I?') answers directly and disarms pending action."""
    session_id = "test_interruption_seq"
    student_user = {"id": 2, "name": "Rahul Sharma", "email": "student@sports.edu", "role": "student"}

    # Arm a booking
    process_query("Book cricket tomorrow at 6 AM", student_user, session_id=session_id)
    
    # User asks unrelated question
    resp_interrupted = process_query("Who am I?", student_user, session_id=session_id)
    assert resp_interrupted.intent == "who_am_i"
    assert "Rahul Sharma" in resp_interrupted.message

    # Verify pending action was disarmed
    session = get_or_create_session(session_id, 2)
    assert session["pending_action"] is None

    # Saying 'Yes' now does NOT create an accidental booking
    resp_yes = process_query("Yes", student_user, session_id=session_id)
    assert resp_yes.intent != "booking_confirmed"

def test_pending_action_ttl_expiration():
    """Verify that a pending confirmation older than 10 minutes expires automatically."""
    session_id = "test_ttl_expiration_seq"
    student_user = {"id": 2, "name": "Rahul Sharma", "email": "student@sports.edu", "role": "student"}

    # Arm a booking
    process_query("Book table tennis tomorrow at 4 PM", student_user, session_id=session_id)
    
    session = get_or_create_session(session_id, 2)
    assert session["pending_action"] is not None

    # Simulate timestamp 15 minutes ago (exceeding 10 min TTL)
    session["pending_action"]["timestamp"] = datetime.now() - timedelta(minutes=15)

    # User attempts to confirm after expiration
    resp_expired = process_query("Yes", student_user, session_id=session_id)
    assert resp_expired.intent == "pending_action_expired"
    assert "expired" in resp_expired.message.lower()
    assert session["pending_action"] is None
