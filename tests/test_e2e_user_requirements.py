import pytest
from app.database import get_db_connection
import app.query_agent as qa

def test_req_01_new_student_attendance_zero_percent(client):
    """Test 1: Newly registered student with 0 sessions has 0.0% attendance rate."""
    client.post("/auth/register", json={
        "name": "Aarav Gupta",
        "email": "aarav@sports.edu",
        "password": "aaravpassword",
        "role": "student"
    })
    login_resp = client.post("/auth/login", json={"email": "aarav@sports.edu", "password": "aaravpassword"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post("/agent/query", json={"query": "What is my attendance percentage?", "session_id": "s1"}, headers=headers)
    data = resp.json()
    assert data["intent"] == "get_user_attendance"
    assert "0.0%" in data["message"] or "0%" in data["message"]

def test_req_02_and_03_dynamic_attendance_percentage(client):
    """Test 2 & 3: Attendance percentage updates dynamically after check-in."""
    login_resp = client.post("/auth/login", json={"email": "aarav@sports.edu", "password": "aaravpassword"})
    token = login_resp.json()["access_token"]
    aarav_id = login_resp.json()["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1 present session -> 100%
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO bookings (user_id, facility_id, sport_id, booking_date, time_slot, status) VALUES (?, 1, 2, '2026-08-25', '06:00 - 07:00', 'completed')", (aarav_id,))
    b1_id = c.lastrowid
    c.execute("INSERT INTO attendance (booking_id, user_id, status, marked_by) VALUES (?, ?, 'present', 1)", (b1_id, aarav_id))
    conn.commit()
    conn.close()

    resp = client.post("/agent/query", json={"query": "Show my attendance", "session_id": "s1"}, headers=headers)
    assert "100.0%" in resp.json()["message"]

    # 1 absent session -> 50.0%
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO bookings (user_id, facility_id, sport_id, booking_date, time_slot, status) VALUES (?, 1, 2, '2026-08-26', '06:00 - 07:00', 'completed')", (aarav_id,))
    b2_id = c.lastrowid
    c.execute("INSERT INTO attendance (booking_id, user_id, status, marked_by) VALUES (?, ?, 'absent', 1)", (b2_id, aarav_id))
    conn.commit()
    conn.close()

    resp2 = client.post("/agent/query", json={"query": "What is my attendance percentage?", "session_id": "s1"}, headers=headers)
    assert "50.0%" in resp2.json()["message"]

def test_req_04_to_07_booking_search_and_cancellation(client, student_token):
    """Test 4, 5, 6, 7: Student search bookings, cancel latest booking, upcoming and cancelled filters."""
    headers = {"Authorization": f"Bearer {student_token}"}
    
    # 4. Show my bookings
    q4 = client.post("/agent/query", json={"query": "Show my bookings", "session_id": "s2"}, headers=headers).json()
    assert q4["intent"] == "search_my_bookings"
    assert q4["success"] is True

    # 5. Cancel latest booking
    q5 = client.post("/agent/query", json={"query": "Cancel my latest booking", "session_id": "s2"}, headers=headers).json()
    assert q5["intent"] == "cancel_booking"
    assert q5["success"] is True

    # 6. Show my upcoming bookings
    q6 = client.post("/agent/query", json={"query": "Show my upcoming bookings", "session_id": "s2"}, headers=headers).json()
    assert q6["intent"] == "search_my_bookings"

    # 7. Show my cancelled bookings
    q7 = client.post("/agent/query", json={"query": "Show my cancelled bookings", "session_id": "s2"}, headers=headers).json()
    assert q7["intent"] == "search_my_bookings"
    assert "cancelled" in q7["message"]

def test_req_08_to_12_conversational_booking_and_conflict_resolution(client, student_token):
    """Test 8, 9, 10, 11, 12: Slot check, follow-up book, confirmation, conflict detection, and alternative recommendation."""
    headers = {"Authorization": f"Bearer {student_token}"}

    # 8. What slots are available
    q8 = client.post("/agent/query", json={"query": "What badminton slots are available tomorrow?", "session_id": "flow_session"}, headers=headers).json()
    assert q8["intent"] == "check_available_slots"
    assert "08:00 - 09:00" in q8["message"]

    # 9. Book 08:00 - 09:00 (Context inheritance)
    q9 = client.post("/agent/query", json={"query": "Book 08:00 - 09:00", "session_id": "flow_session"}, headers=headers).json()
    assert q9["intent"] == "confirm_booking_request"
    assert q9["pending_confirmation"] is True
    assert "Badminton" in q9["message"]

    # 9.1 Confirm
    q9_conf = client.post("/agent/query", json={"query": "Yes", "session_id": "flow_session"}, headers=headers).json()
    assert q9_conf["intent"] == "booking_confirmed"
    assert q9_conf["success"] is True

    # 10. Book badminton tomorrow at 5 PM
    q10 = client.post("/agent/query", json={"query": "Book badminton tomorrow at 5 PM", "session_id": "s3"}, headers=headers).json()
    assert q10["intent"] == "confirm_booking_request"
    assert "17:00 - 18:00" in q10["message"]

    # Confirm booking 10 (Court 1)
    client.post("/agent/query", json={"query": "Yes", "session_id": "s3"}, headers=headers)

    # Book Court 2 as well for the same slot by another student (User #3) so all badminton courts are occupied
    from datetime import date, timedelta
    tomorrow_str = (date.today() + timedelta(days=1)).isoformat()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO bookings (user_id, facility_id, sport_id, booking_date, time_slot, status) VALUES (3, 3, 2, ?, '17:00 - 18:00', 'confirmed')",
        (tomorrow_str,)
    )
    conn.commit()
    conn.close()

    # 11. Conflict detection & alternative slots
    q11 = client.post("/agent/query", json={"query": "Book badminton tomorrow at 5 PM", "session_id": "conflict_session"}, headers=headers).json()
    assert q11["intent"] == "slot_conflict_alternatives"
    assert q11["success"] is False
    assert len(q11.get("suggested_slots", [])) > 0

    # 12. Follow-up booking of recommended slot
    q12 = client.post("/agent/query", json={"query": "Book 6 PM", "session_id": "conflict_session"}, headers=headers).json()
    assert q12["intent"] == "confirm_booking_request"
    assert "18:00 - 19:00" in q12["message"]

def test_req_13_to_17_student_attendance_and_rbac_denial(client, student_token):
    """Test 13, 14, 15, 16, 17: Attendance check and student permission denials on admin operations."""
    headers = {"Authorization": f"Bearer {student_token}"}

    # 13. Show my attendance
    q13 = client.post("/agent/query", json={"query": "Show my attendance", "session_id": "s4"}, headers=headers).json()
    assert q13["intent"] == "get_user_attendance"

    # 14. Attendance percentage
    q14 = client.post("/agent/query", json={"query": "What is my attendance percentage?", "session_id": "s4"}, headers=headers).json()
    assert q14["intent"] == "get_user_attendance"

    # 15. Student "Show all users" -> Denied
    q15 = client.post("/agent/query", json={"query": "Show all users", "session_id": "s5"}, headers=headers).json()
    assert q15["intent"] == "admin_command_denied"
    assert q15["success"] is False

    # 16. Student "Block user 3" -> Denied
    q16 = client.post("/agent/query", json={"query": "Block user 3", "session_id": "s5"}, headers=headers).json()
    assert q16["intent"] == "admin_command_denied"
    assert q16["success"] is False

    # 17. Student "Unblock user 3" -> Denied
    q17 = client.post("/agent/query", json={"query": "Unblock user 3", "session_id": "s5"}, headers=headers).json()
    assert q17["intent"] == "admin_command_denied"
    assert q17["success"] is False

def test_req_18_to_20_admin_operations_and_user_governance(client, admin_token):
    """Test 18, 19, 20: Admin user management (show all users, block user, unblock user)."""
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 18. Admin "Show all users" -> Success
    q18 = client.post("/agent/query", json={"query": "Show all users", "session_id": "adm_s"}, headers=headers).json()
    assert q18["intent"] == "list_all_users"
    assert q18["success"] is True

    # 19. Admin "Block user 3" -> Armed confirmation & executed
    q19 = client.post("/agent/query", json={"query": "Block user 3", "session_id": "adm_block"}, headers=headers).json()
    assert q19["intent"] == "confirm_block_user"
    assert q19["pending_confirmation"] is True
    q19_conf = client.post("/agent/query", json={"query": "Yes", "session_id": "adm_block"}, headers=headers).json()
    assert q19_conf["intent"] == "user_blocked"
    assert q19_conf["success"] is True

    # 20. Admin "Unblock user 3" -> Success
    q20 = client.post("/agent/query", json={"query": "Unblock user 3", "session_id": "adm_unblock"}, headers=headers).json()
    assert q20["intent"] == "user_unblocked"
    assert q20["success"] is True

def test_req_21_to_25_context_isolation_auth_and_lockout(client, admin_token, student_token):
    """Test 21 to 25: Clear chat isolation, duplicate registration, re-login, blocked login lockout, unblocked login."""
    headers = {"Authorization": f"Bearer {student_token}"}
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 21. Clear Chat / context isolation
    new_sess_id = "cleared_session_e2e"
    q21 = client.post("/agent/query", json={"query": "Who am I logged in as?", "session_id": new_sess_id}, headers=headers).json()
    assert q21["intent"] == "who_am_i"
    b_check = client.get("/bookings", headers=headers).json()
    assert len(b_check) > 0

    # 22. Duplicate registration rejected
    dup_resp = client.post("/auth/register", json={
        "name": "Aarav Gupta",
        "email": "aarav@sports.edu",
        "password": "anotherpassword",
        "role": "student"
    })
    assert dup_resp.status_code == 400

    # 23. Existing user login
    login_again = client.post("/auth/login", json={"email": "aarav@sports.edu", "password": "aaravpassword"})
    assert login_again.status_code == 200

    # 24. Blocked user login rejected (403 Forbidden)
    client.patch("/auth/users/3/block", headers=admin_headers)
    blocked_login = client.post("/auth/login", json={"email": "priya@sports.edu", "password": "priya123"})
    assert blocked_login.status_code == 403

    # 25. Unblocked user login success
    client.patch("/auth/users/3/unblock", headers=admin_headers)
    unblocked_login = client.post("/auth/login", json={"email": "priya@sports.edu", "password": "priya123"})
    assert unblocked_login.status_code == 200
