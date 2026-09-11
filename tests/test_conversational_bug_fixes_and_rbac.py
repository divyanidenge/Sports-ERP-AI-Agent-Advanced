import pytest
from datetime import date, timedelta
from app.database import get_db_connection
from app.agent_tools import create_booking_tool

def test_ambiguous_cancellation_with_multiple_active_bookings(client, student_token):
    """Test that ambiguous cancellation with multiple active bookings triggers disambiguation without auto-cancelling."""
    headers = {"Authorization": f"Bearer {student_token}"}
    ambig_date = (date.today() + timedelta(days=11)).isoformat()
    
    # 1. Create two active bookings for the student on ambig_date
    resp1 = client.post("/bookings", json={
        "facility_id": 1,
        "sport_id": 1,
        "booking_date": ambig_date,
        "time_slot": "06:00 - 07:00",
        "notes": "Slot 1"
    }, headers=headers)
    assert resp1.status_code == 200
    
    resp2 = client.post("/bookings", json={
        "facility_id": 2,
        "sport_id": 1,
        "booking_date": ambig_date,
        "time_slot": "07:00 - 08:00",
        "notes": "Slot 2"
    }, headers=headers)
    assert resp2.status_code == 200
    
    # 2. Query ambiguous cancellation
    q_resp = client.post("/agent/query", json={
        "query": f"Cancel my booking on {ambig_date}",
        "session_id": "test_ambig_cancel"
    }, headers=headers).json()
    
    assert q_resp["intent"] == "disambiguate_booking_cancellation"
    assert q_resp["success"] is True
    assert "candidate_bookings" in q_resp["data"]
    assert len(q_resp["data"]["candidate_bookings"]) >= 2
    
    # Verify neither booking was cancelled prematurely
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM bookings WHERE user_id = 2 AND booking_date = ? AND status = 'confirmed'", (ambig_date,))
    assert cursor.fetchone()["cnt"] >= 2
    conn.close()

def test_ambiguous_badminton_cancellation_shows_active_only(client, student_token):
    """Test that options-to-cancel queries return only confirmed/active bookings and never cancelled ones."""
    headers = {"Authorization": f"Bearer {student_token}"}
    target_date = (date.today() + timedelta(days=2)).isoformat()
    
    # 1. Create a confirmed badminton booking
    resp1 = client.post("/bookings", json={
        "facility_id": 2,
        "sport_id": 2,
        "booking_date": target_date,
        "time_slot": "09:00 - 10:00",
        "notes": "Badminton Active"
    }, headers=headers)
    assert resp1.status_code == 200
    
    # 2. Create another badminton booking and then cancel it
    resp2 = client.post("/bookings", json={
        "facility_id": 3,
        "sport_id": 2,
        "booking_date": target_date,
        "time_slot": "10:00 - 11:00",
        "notes": "Badminton To Cancel"
    }, headers=headers)
    assert resp2.status_code == 200
    b2_id = resp2.json()["id"]
    
    # Cancel second booking directly
    client.delete(f"/bookings/{b2_id}", headers=headers)
    
    # 3. Ask ambiguous cancellation / options for badminton
    q_resp = client.post("/agent/query", json={
        "query": f"I can't remember which badminton booking I have on {target_date}. Show me my options and cancel the one I choose.",
        "session_id": "test_badminton_options"
    }, headers=headers).json()
    
    assert q_resp["intent"] == "disambiguate_booking_cancellation"
    assert q_resp["success"] is True
    candidates = q_resp["data"]["candidate_bookings"]
    assert len(candidates) == 1
    assert candidates[0]["sport_name"].lower() == "badminton"
    assert candidates[0]["booking_date"] == target_date
    assert candidates[0]["id"] != b2_id

def test_student_privacy_rbac_denial(client, student_token):
    """Test that students are denied access when querying all students or other users' bookings."""
    headers = {"Authorization": f"Bearer {student_token}"}
    
    # 1. Student asks for all students' bookings
    q_all = client.post("/agent/query", json={
        "query": "Show all students' bookings",
        "session_id": "test_rbac_student_all"
    }, headers=headers).json()
    assert q_all["intent"] == "access_denied"
    assert q_all["success"] is False
    assert "permission" in q_all["message"].lower() or "denied" in q_all["message"].lower()
    
    # 2. Student asks for another user's bookings (e.g. Vikram / Priya)
    q_other = client.post("/agent/query", json={
        "query": "Show Vikram's bookings",
        "session_id": "test_rbac_student_other"
    }, headers=headers).json()
    assert q_other["intent"] == "access_denied"
    assert q_other["success"] is False

def test_admin_user_queries_and_named_resolution(client, admin_token):
    """Test that admin can query all students' bookings and resolve specific users by name."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # 1. Admin queries all campus bookings
    q_all = client.post("/agent/query", json={
        "query": "Show all students' bookings",
        "session_id": "test_admin_all"
    }, headers=headers).json()
    assert q_all["intent"] == "get_all_bookings"
    assert q_all["success"] is True
    assert isinstance(q_all["data"], list)
    
    # 2. Admin queries specific student by name (Rahul)
    q_rahul = client.post("/agent/query", json={
        "query": "Show Rahul's bookings",
        "session_id": "test_admin_named_rahul"
    }, headers=headers).json()
    assert q_rahul["intent"] == "admin_view_user_bookings"
    assert q_rahul["success"] is True
    assert "Rahul" in q_rahul["message"]
    
    # 3. Admin queries non-existent user
    q_none = client.post("/agent/query", json={
        "query": "Show NonExistentPerson's bookings",
        "session_id": "test_admin_non_existent"
    }, headers=headers).json()
    assert q_none["intent"] == "user_not_found"
    assert q_none["success"] is False

def test_individual_analytics_nl_routing(client, admin_token):
    """Test individual natural language analytics questions."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # 1. Highest utilization
    q_util = client.post("/agent/query", json={
        "query": "Which facility has the highest utilization?",
        "session_id": "test_highest_util"
    }, headers=headers).json()
    assert q_util["intent"] == "highest_facility_utilization"
    assert q_util["success"] is True
    assert "Highest Utilized Facility" in q_util["message"]
    
    # 2. Most popular sport
    q_pop = client.post("/agent/query", json={
        "query": "Which sport is most popular?",
        "session_id": "test_most_pop"
    }, headers=headers).json()
    assert q_pop["intent"] == "sport_popularity"
    assert q_pop["success"] is True
    assert "Most Popular Sport" in q_pop["message"]
    
    # 3. Peak booking hours
    q_peak = client.post("/agent/query", json={
        "query": "What are the peak booking hours?",
        "session_id": "test_peak_hours"
    }, headers=headers).json()
    assert q_peak["intent"] == "peak_booking_hours"
    assert q_peak["success"] is True
    assert "Peak Booking Hours" in q_peak["message"]

def test_comprehensive_benchmark_nl_routing(client, admin_token, student_token):
    """Test comprehensive benchmark natural language trigger and student RBAC denial."""
    # Admin allowed
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    q_admin = client.post("/agent/query", json={
        "query": "Run the comprehensive benchmark",
        "session_id": "test_bench_admin"
    }, headers=admin_headers).json()
    assert q_admin["intent"] == "run_comprehensive_benchmark"
    assert q_admin["success"] is True
    assert "Benchmark Results" in q_admin["message"]
    
    # Student denied
    student_headers = {"Authorization": f"Bearer {student_token}"}
    q_student = client.post("/agent/query", json={
        "query": "Run the comprehensive benchmark",
        "session_id": "test_bench_student"
    }, headers=student_headers).json()
    assert q_student["intent"] == "admin_command_denied"
    assert q_student["success"] is False

def test_audit_and_provenance_nl_routing(client, admin_token, student_token):
    """Test audit log and cryptographic provenance verification query routing."""
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    
    # 1. Admin views audit logs
    q_audit = client.post("/agent/query", json={
        "query": "Show me the audit logs",
        "session_id": "test_show_audit"
    }, headers=admin_headers).json()
    assert q_audit["intent"] == "show_audit_logs"
    assert q_audit["success"] is True
    
    # 2. Admin verifies provenance for audit record #1
    q_prov = client.post("/agent/query", json={
        "query": "Verify provenance for audit 1",
        "session_id": "test_verify_prov"
    }, headers=admin_headers).json()
    assert q_prov["intent"] == "verify_provenance"
    assert "Provenance Verified" in q_prov["message"]
    
    # 3. Student denied audit logs
    student_headers = {"Authorization": f"Bearer {student_token}"}
    q_denied = client.post("/agent/query", json={
        "query": "Show me the audit logs",
        "session_id": "test_audit_student"
    }, headers=student_headers).json()
    assert q_denied["intent"] == "admin_command_denied"
    assert q_denied["success"] is False

def test_idempotency_key_persistence_and_duplicate_prevention(client, student_token):
    """Test that idempotency_key is persisted and duplicate requests return existing booking."""
    target_date = (date.today() + timedelta(days=5)).isoformat()
    
    # Direct tool call
    res = create_booking_tool(
        user_id=2,
        sport_name="Cricket",
        booking_date=target_date,
        time_slot="16:00 - 17:00",
        notes="Practice match"
    )
    assert res["success"] is True
    b_data = res["data"]
    assert b_data["idempotency_key"] is not None
    assert "ai-book-2-" in b_data["idempotency_key"]
    
    # Check in database
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT idempotency_key FROM bookings WHERE id = ?", (b_data["id"],))
    row = cursor.fetchone()
    assert row["idempotency_key"] == b_data["idempotency_key"]
    conn.close()

def test_student_privacy_rbac_all_forbidden_cases(client, student_token):
    """Test all specific variations of student access violations:
    'Show Rahul's bookings', 'Show Vikram's bookings', 'Show all students' bookings',
    'Show all users' bookings', 'Show another student's bookings', 'Show bookings of user 7'"""
    headers = {"Authorization": f"Bearer {student_token}"}
    forbidden_queries = [
        "Show Rahul's bookings",
        "Show Vikram's bookings",
        "Show all students' bookings",
        "Show all users' bookings",
        "Show another student's bookings",
        "Show bookings of user 7"
    ]
    for q in forbidden_queries:
        r = client.post("/agent/query", json={"query": q, "session_id": "test_priv_all"}, headers=headers).json()
        assert r["intent"] == "access_denied", f"Failed on query: {q}"
        assert r["success"] is False
        assert "Access Denied" in r["message"] or "permission" in r["message"].lower()

def test_multiturn_cancellation_selection_flow(client, student_token):
    """Test multi-turn candidate cancellation:
    Turn 1: 'I can't remember which badminton booking I have tomorrow. Show me my options and cancel the one I choose.'
    Turn 2: 'I choose option 2'
    Verifies that option 2 is cancelled and previous candidate context is preserved."""
    headers = {"Authorization": f"Bearer {student_token}"}
    test_d = (date.today() + timedelta(days=6)).isoformat()
    session_id = "test_multiturn_cancel_session"
    
    # Create 2 badminton bookings
    r1 = client.post("/bookings", json={
        "facility_id": 2,
        "sport_id": 2,
        "booking_date": test_d,
        "time_slot": "07:00 - 08:00",
        "notes": "Slot A"
    }, headers=headers).json()
    r2 = client.post("/bookings", json={
        "facility_id": 3,
        "sport_id": 2,
        "booking_date": test_d,
        "time_slot": "08:00 - 09:00",
        "notes": "Slot B"
    }, headers=headers).json()
    
    b1_id, b2_id = r1["id"], r2["id"]
    
    # Turn 1: Options request
    q1 = client.post("/agent/query", json={
        "query": f"I can't remember which badminton booking I have on {test_d}. Show me my options and cancel the one I choose.",
        "session_id": session_id
    }, headers=headers).json()
    assert q1["intent"] == "disambiguate_booking_cancellation"
    assert q1["success"] is True
    assert len(q1["data"]["candidate_bookings"]) == 2
    
    # Turn 2: Choose option 2
    q2 = client.post("/agent/query", json={
        "query": "I choose option 2",
        "session_id": session_id
    }, headers=headers).json()
    assert q2["intent"] == "cancel_booking"
    assert q2["success"] is True
    
    # Verify in DB: b2 cancelled, b1 active
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, status FROM bookings WHERE id IN (?, ?)", (b1_id, b2_id))
    rows = {r["id"]: r["status"] for r in c.fetchall()}
    conn.close()
    assert rows[b2_id] == "cancelled"
    assert rows[b1_id] == "confirmed"

def test_combined_multimetric_analytics_nlp(client, admin_token):
    """Test: 'Analyze facility utilization, identify the most popular sport, and show peak booking hours.'"""
    headers = {"Authorization": f"Bearer {admin_token}"}
    q = client.post("/agent/query", json={
        "query": "Analyze facility utilization, identify the most popular sport, and show peak booking hours.",
        "session_id": "test_combined_nlp"
    }, headers=headers).json()
    assert q["intent"] == "combined_analytics"
    assert q["success"] is True
    assert "Comprehensive Sports ERP Analytics Breakdown" in q["message"]
    assert "Facility Utilization" in q["message"]
    assert "Most Popular Sport" in q["message"]
    assert "Peak Booking Hours" in q["message"]

def test_evening_conversational_booking_flow(client, student_token):
    """Test: 'I want to play badminton tomorrow evening. Find an available slot for me and book it.'
    Arms confirmation for evening slot, confirms on 'Yes'."""
    headers = {"Authorization": f"Bearer {student_token}"}
    session_id = "test_evening_booking_flow"
    eve_date = (date.today() + timedelta(days=9)).isoformat()
    
    q1 = client.post("/agent/query", json={
        "query": f"I want to play badminton on {eve_date} evening. Find an available slot for me and book it.",
        "session_id": session_id
    }, headers=headers).json()
    
    assert q1["intent"] == "confirm_booking_request"
    assert q1["pending_confirmation"] is True
    assert "17:00 - 18:00" in q1["message"] or "18:00 - 19:00" in q1["message"] or "16:00 - 17:00" in q1["message"]
    
    # Affirm booking
    q2 = client.post("/agent/query", json={
        "query": "Yes",
        "session_id": session_id
    }, headers=headers).json()
    assert q2["intent"] == "booking_confirmed"
    assert q2["success"] is True
    assert q2["data"]["idempotency_key"] is not None

def test_student_daily_quota_limit_c6(client, student_token):
    """Test Rule C6: Student cannot hold more than 2 bookings per day."""
    headers = {"Authorization": f"Bearer {student_token}"}
    quota_date = (date.today() + timedelta(days=8)).isoformat()
    
    # 1. First booking -> Success
    r1 = client.post("/bookings", json={
        "facility_id": 1,
        "sport_id": 1,
        "booking_date": quota_date,
        "time_slot": "06:00 - 07:00"
    }, headers=headers)
    assert r1.status_code == 200
    
    # 2. Second booking -> Success
    r2 = client.post("/bookings", json={
        "facility_id": 2,
        "sport_id": 2,
        "booking_date": quota_date,
        "time_slot": "07:00 - 08:00"
    }, headers=headers)
    assert r2.status_code == 200
    
    # 3. Third booking -> Rejected by Constraint Engine (C6)
    r3 = client.post("/bookings", json={
        "facility_id": 3,
        "sport_id": 2,
        "booking_date": quota_date,
        "time_slot": "08:00 - 09:00"
    }, headers=headers)
    assert r3.status_code == 400
    assert "quota" in r3.json()["detail"].lower() or "limit" in r3.json()["detail"].lower()

def test_sql_sandbox_mutation_blocking_all_keywords():
    """Test that SQL sandbox strictly blocks all mutating, DDL, and PRAGMA keywords."""
    from app.eval_benchmark import sanitize_and_validate_sql
    
    forbidden_sql_statements = [
        "INSERT INTO bookings (user_id) VALUES (1)",
        "UPDATE bookings SET status='cancelled'",
        "DELETE FROM bookings WHERE id=1",
        "DROP TABLE users",
        "ALTER TABLE facilities ADD COLUMN test TEXT",
        "CREATE TABLE test (id INT)",
        "TRUNCATE TABLE audit_logs",
        "PRAGMA table_info(users)",
        "SELECT * FROM bookings; DROP TABLE users;"
    ]
    for stmt in forbidden_sql_statements:
        is_safe, msg = sanitize_and_validate_sql(stmt)
        assert is_safe is False, f"Sandbox failed to block: {stmt}"
        assert "Security Violation" in msg

def test_multi_turn_cancellation_explicit_sport_filter_zero_candidates(client, student_token):
    """Test: When user specifies sport with 0 active bookings, returns clean not-found without hallucinating candidates."""
    headers = {"Authorization": f"Bearer {student_token}"}
    target_d = (date.today() + timedelta(days=12)).isoformat()
    
    # Create a football booking only on target_d
    client.post("/bookings", json={
        "facility_id": 5,
        "sport_id": 4,
        "booking_date": target_d,
        "time_slot": "16:00 - 17:00"
    }, headers=headers)

    # Ask for badminton options (where user has 0 bookings)
    q = client.post("/agent/query", json={
        "query": f"I can't remember which badminton booking I have on {target_d}. Show me my options and cancel the one I choose.",
        "session_id": "test_badm_zero_candidates"
    }, headers=headers).json()

    assert q["intent"] == "cancel_booking_not_found"
    assert q["success"] is False
    assert len(q.get("data", {}).get("candidate_bookings", [])) == 0
    assert "badminton" in q["message"].lower()

    # Clean up test booking
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM bookings WHERE user_id = 2 AND booking_date = ?", (target_d,))
    conn.commit()
    conn.close()

def test_ordinal_and_booking_id_followup_cancellation(client, student_token):
    """Test: After candidate disambiguation, follow-up with 'id 41' or 'ID 41' safely cancels that candidate."""
    headers = {"Authorization": f"Bearer {student_token}"}
    target_d = (date.today() + timedelta(days=13)).isoformat()
    session_id = "test_id_followup_session"
    
    # Create two active bookings
    r1 = client.post("/bookings", json={"facility_id": 1, "sport_id": 1, "booking_date": target_d, "time_slot": "06:00 - 07:00"}, headers=headers).json()
    r2 = client.post("/bookings", json={"facility_id": 1, "sport_id": 1, "booking_date": target_d, "time_slot": "07:00 - 08:00"}, headers=headers).json()
    b1_id = r1["id"]
    b2_id = r2["id"]

    # Step 1: Disambiguation prompt
    q1 = client.post("/agent/query", json={
        "query": f"Cancel my cricket booking on {target_d}",
        "session_id": session_id
    }, headers=headers).json()
    assert q1["intent"] == "disambiguate_booking_cancellation"

    # Step 2: Follow-up with 'id <b1_id>'
    q2 = client.post("/agent/query", json={
        "query": f"id {b1_id}",
        "session_id": session_id
    }, headers=headers).json()
    assert q2["intent"] == "cancel_booking"
    assert q2["success"] is True

    # Verify in DB and clean up
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT status FROM bookings WHERE id = ?", (b1_id,))
    assert c.fetchone()["status"] == "cancelled"
    c.execute("DELETE FROM bookings WHERE id IN (?, ?)", (b1_id, b2_id))
    conn.commit()
    conn.close()

def test_restore_cancelled_booking_flow_and_audit(client, student_token):
    """Test: Restore cancelled booking restores confirmed status and records cryptographic audit log."""
    headers = {"Authorization": f"Bearer {student_token}"}
    target_d = (date.today() + timedelta(days=14)).isoformat()
    
    # 1. Create and cancel a booking
    r = client.post("/bookings", json={"facility_id": 2, "sport_id": 2, "booking_date": target_d, "time_slot": "06:00 - 07:00"}, headers=headers).json()
    b_id = r["id"]
    client.delete(f"/bookings/{b_id}", headers=headers)

    # 2. Restore booking via NLP
    q = client.post("/agent/query", json={
        "query": f"restore the booking id {b_id}",
        "session_id": "test_restore_session"
    }, headers=headers).json()
    assert q["intent"] == "restore_booking"
    assert q["success"] is True
    assert "restored successfully" in q["message"].lower()

    # 3. Verify status in DB
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT status FROM bookings WHERE id = ?", (b_id,))
    assert c.fetchone()["status"] == "confirmed"

    # 4. Verify audit log entry
    c.execute("SELECT action, provenance_token FROM audit_logs WHERE action = 'BOOKING_RESTORED' AND resource_id = ?", (b_id,))
    audit_row = c.fetchone()
    assert audit_row is not None
    assert audit_row["provenance_token"] is not None
    c.execute("DELETE FROM bookings WHERE id = ?", (b_id,))
    conn.commit()
    conn.close()

def test_invalid_booking_temporal_and_operating_hours_validation(client, student_token):
    """Test: Booking attempts for past dates or outside operating hours fail without arming confirmation."""
    headers = {"Authorization": f"Bearer {student_token}"}

    # 1. Past date attempt
    q_past = client.post("/agent/query", json={
        "query": "Book badminton on 2020-01-01",
        "session_id": "test_past_val"
    }, headers=headers).json()
    assert q_past["intent"] == "booking_failed"
    assert q_past["success"] is False
    assert q_past.get("pending_confirmation") in [None, False]

    # 2. Out of operating hours attempt (11 PM)
    q_ooh = client.post("/agent/query", json={
        "query": "Book badminton tomorrow at 11 PM",
        "session_id": "test_ooh_val"
    }, headers=headers).json()
    assert q_ooh["intent"] in ["booking_failed", "slot_conflict_alternatives"]
    assert q_ooh["success"] is False
    assert q_ooh.get("pending_confirmation") in [None, False]
    assert len(q_ooh.get("suggested_slots", [])) > 0

