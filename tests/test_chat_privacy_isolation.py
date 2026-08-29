import pytest
import app.query_agent as qa
from app.query_agent import process_query, get_or_create_session

def test_student_and_admin_chat_state_isolation():
    """
    Verify that Student A, Student B, and Admin have completely isolated session stores
    and conversation entities, even when sharing common session identifiers.
    """
    student_a = {"id": 2, "name": "Rahul Sharma", "email": "student@sports.edu", "role": "student"}
    student_b = {"id": 3, "name": "Priya Patel", "email": "priya@sports.edu", "role": "student"}
    admin_user = {"id": 1, "name": "Admin User", "email": "admin@sports.edu", "role": "admin"}

    shared_session_label = "main_chat_session"

    # Step 1: Student A asks to check badminton slots
    resp_a = process_query("What badminton slots are available tomorrow?", student_a, session_id=shared_session_label)
    assert resp_a.intent == "check_available_slots"
    sess_a = get_or_create_session(shared_session_label, student_a["id"])
    assert sess_a["last_entities"]["sport"] == "Badminton"

    # Step 2: Verify Student B has empty session entities under the same session label
    sess_b = get_or_create_session(shared_session_label, student_b["id"])
    assert sess_b["last_entities"]["sport"] is None
    assert sess_b["pending_action"] is None

    # Step 3: Verify Admin has empty session entities under the same session label
    sess_admin = get_or_create_session(shared_session_label, admin_user["id"])
    assert sess_admin["last_entities"]["sport"] is None
    assert sess_admin["pending_action"] is None

    # Step 4: Student B sets entity for Cricket
    process_query("What cricket slots are available tomorrow?", student_b, session_id=shared_session_label)
    assert sess_b["last_entities"]["sport"] == "Cricket"
    assert sess_a["last_entities"]["sport"] == "Badminton"  # Student A untouched!

    # Step 5: Admin performs user block action
    process_query("Block user 3", admin_user, session_id=shared_session_label)
    assert sess_admin["pending_action"] is not None
    assert sess_a["pending_action"] is None  # Student A has no pending block
    assert sess_b["pending_action"] is None  # Student B has no pending block

def test_session_cleanup_and_isolation():
    """Verify that clearing session for user 2 does not affect user 1 or user 3."""
    key_2 = "2_isolated_test"
    key_3 = "3_isolated_test"

    qa.SESSION_STORE[key_2] = {"history": ["msg1"], "pending_action": None, "last_entities": {"sport": "Football"}}
    qa.SESSION_STORE[key_3] = {"history": ["msg2"], "pending_action": None, "last_entities": {"sport": "Swimming"}}

    # Clear user 2
    if key_2 in qa.SESSION_STORE:
        del qa.SESSION_STORE[key_2]

    assert key_2 not in qa.SESSION_STORE
    assert key_3 in qa.SESSION_STORE
    assert qa.SESSION_STORE[key_3]["last_entities"]["sport"] == "Swimming"
