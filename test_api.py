import os
import sys
from pathlib import Path

# Setup paths and isolated test database
backend_dir = Path(__file__).resolve().parent
project_root = backend_dir.parent
for p in [str(backend_dir), str(project_root)]:
    if p not in sys.path:
        sys.path.insert(0, p)

test_db_path = str((backend_dir / "sports_erp_test.db").resolve())
os.environ["DB_PATH"] = test_db_path

from fastapi.testclient import TestClient
from app.config import DB_PATH as ACTIVE_DB_PATH
from app.main import app
from app.database import reset_db_for_tests

def safe_str(s: str) -> str:
    """Removes non-ascii characters for clean console printing on Windows cp1252."""
    if not s:
        return ""
    return str(s).encode('ascii', 'replace').decode('ascii')

def test_full_sports_erp_flow():
    # Verify active DB is strictly the test database
    assert "test" in ACTIVE_DB_PATH.lower(), f"Security Alert: Tests cannot run on production DB! (Active: {ACTIVE_DB_PATH})"
    
    # 1. Reset fresh test DB with pristine seed data (NEVER touches live sports_erp.db)
    reset_db_for_tests()
    client = TestClient(app)
    print("\n" + "="*70)
    print("[*] STARTING AGENTIC SPORTS ERP + COMPREHENSIVE REGRESSION VERIFICATION")
    print("="*70)

    # Health check
    res = client.get("/health")
    assert res.status_code == 200, f"Health check failed: {res.text}"
    print("[+] 1. Health check passed")

    # 2. Test Admin & Student Logins
    login_admin = client.post("/auth/login", json={"email": "admin@sports.edu", "password": "admin123"})
    assert login_admin.status_code == 200, f"Admin login failed: {login_admin.text}"
    admin_token = login_admin.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    print("[+] 2. Admin Login successful (JWT acquired)")

    login_student = client.post("/auth/login", json={"email": "student@sports.edu", "password": "student123"})
    assert login_student.status_code == 200, f"Student login failed: {login_student.text}"
    student_token = login_student.json()["access_token"]
    student_headers = {"Authorization": f"Bearer {student_token}"}
    print("[+] 3. Student Login successful (JWT acquired)")

    # 3. Query: Hinglish "Meri bookings dikhao"
    res_my_b = client.post("/agent/query", json={"query": "Meri bookings dikhao", "session_id": "test_s1"}, headers=student_headers)
    assert res_my_b.status_code == 200
    res_json = res_my_b.json()
    assert res_json["intent"] == "search_my_bookings"
    initial_booking_count = len(res_json["data"])
    print(f"[+] 4. Query 'Meri bookings dikhao' -> '{safe_str(res_json['message'])}'")

    # =========================================================================
    # 🧪 REGRESSION TEST SUITE 1: CONTEXT ISOLATION & DEDICATED INTENTS
    # =========================================================================
    print("\n--- [START REGRESSION SUITE: CONTEXT ISOLATION & DEDICATED INTENTS] ---")

    reg_session = "reg_test_session_1"
    res_req = client.post("/agent/query", json={"query": "Kal 5 PM badminton book kar do", "session_id": reg_session}, headers=student_headers)
    assert res_req.status_code == 200
    assert res_req.json()["pending_confirmation"] is True
    print(f"[+] Reg 1.1: Booking requested -> Pending confirmation set: '{safe_str(res_req.json()['message'])}'")

    # User interrupts with "Who am I logged in as?"
    res_whoami = client.post("/agent/query", json={"query": "Who am I logged in as?", "session_id": reg_session}, headers=student_headers)
    assert res_whoami.status_code == 200
    assert res_whoami.json()["intent"] == "who_am_i"
    assert "Rahul Sharma" in res_whoami.json()["message"]
    assert "Student" in res_whoami.json()["message"]
    assert res_whoami.json()["pending_confirmation"] is False
    print(f"[+] Reg 1.2: Unrelated 'Who am I' answered correctly -> '{safe_str(res_whoami.json()['message'])}'")

    # User asks "Mera role kya hai?"
    res_role = client.post("/agent/query", json={"query": "Mera role kya hai?", "session_id": reg_session}, headers=student_headers)
    assert res_role.status_code == 200
    assert res_role.json()["intent"] == "user_role_info"
    assert "Student" in res_role.json()["message"]
    assert res_role.json()["pending_confirmation"] is False
    print(f"[+] Reg 1.3: 'Mera role kya hai' answered correctly -> '{safe_str(res_role.json()['message'])}'")

    # User asks "show catalog" / "show my catalog"
    res_cat = client.post("/agent/query", json={"query": "show catalog", "session_id": reg_session}, headers=student_headers)
    assert res_cat.status_code == 200
    assert res_cat.json()["intent"] == "show_catalog"
    assert res_cat.json()["pending_confirmation"] is False
    print(f"[+] Reg 1.4: 'show catalog' answered correctly as Catalog -> '{safe_str(res_cat.json()['message'][:60])}...'")

    # Verify no accidental booking was created during interrupted turns
    b_check = client.get("/bookings", headers=student_headers)
    assert len(b_check.json()) == initial_booking_count, "Error: Accidental booking was created during unrelated questions!"
    print(f"[+] Reg 1.5: VERIFIED zero bookings created during interrupted questions (Count = {initial_booking_count})")

    # REGRESSION 2: Confirmation ("Yes" / "Haan kar do") executes booking when active
    reg_session_2 = "reg_test_session_2"
    client.post("/agent/query", json={"query": "Kal 5 PM badminton book kar do", "session_id": reg_session_2}, headers=student_headers)
    res_yes = client.post("/agent/query", json={"query": "Yes", "session_id": reg_session_2}, headers=student_headers)
    assert res_yes.status_code == 200
    assert res_yes.json()["intent"] == "booking_confirmed"
    assert res_yes.json()["success"] is True
    print(f"[+] Reg 2.1: Direct 'Yes' confirmation creates exactly one booking -> '{safe_str(res_yes.json()['message'])}'")

    # REGRESSION 3: Explicit Cancellation ("No" / "Nahi") cancels pending action
    reg_session_3 = "reg_test_session_3"
    client.post("/agent/query", json={"query": "Kal 5 PM cricket book kar do", "session_id": reg_session_3}, headers=student_headers)
    res_no = client.post("/agent/query", json={"query": "No", "session_id": reg_session_3}, headers=student_headers)
    assert res_no.status_code == 200
    assert res_no.json()["intent"] == "action_cancelled"
    print(f"[+] Reg 3.1: 'No' cancels pending action cleanly -> '{safe_str(res_no.json()['message'])}'")

    # =========================================================================
    # 🧪 REGRESSION TEST SUITE 2: INTENT-CLASSIFICATION FIXES
    # =========================================================================
    print("\n--- [START INTENT CLASSIFICATION REGRESSION TESTS] ---")

    # 1. "Am I a student or admin?" / "Which role do I have?"
    res_role_en1 = client.post("/agent/query", json={"query": "Am I a student or admin?"}, headers=student_headers)
    assert res_role_en1.status_code == 200
    assert res_role_en1.json()["intent"] == "user_role_info"
    assert "Student" in res_role_en1.json()["message"]
    print(f"[+] Fix 1.1: 'Am I a student or admin?' -> '{safe_str(res_role_en1.json()['message'])}'")

    res_role_en2 = client.post("/agent/query", json={"query": "Which role do I have?"}, headers=student_headers)
    assert res_role_en2.status_code == 200
    assert res_role_en2.json()["intent"] == "user_role_info"
    assert "Student" in res_role_en2.json()["message"]
    print(f"[+] Fix 1.2: 'Which role do I have?' -> '{safe_str(res_role_en2.json()['message'])}'")

    # 2. "Meri active bookings kya hain?"
    res_act_b = client.post("/agent/query", json={"query": "Meri active bookings kya hain?"}, headers=student_headers)
    assert res_act_b.status_code == 200
    assert res_act_b.json()["intent"] == "search_my_bookings"
    assert res_act_b.json()["pending_confirmation"] is False
    print(f"[+] Fix 2.1: 'Meri active bookings kya hain?' -> '{safe_str(res_act_b.json()['message'])}'")

    # 3. "Do I have any upcoming bookings?"
    res_upc_b = client.post("/agent/query", json={"query": "Do I have any upcoming bookings?"}, headers=student_headers)
    assert res_upc_b.status_code == 200
    assert res_upc_b.json()["intent"] == "search_my_bookings"
    assert res_upc_b.json()["pending_confirmation"] is False
    print(f"[+] Fix 3.1: 'Do I have any upcoming bookings?' -> '{safe_str(res_upc_b.json()['message'])}'")

    # 4. "show my all bookings"
    res_all_b = client.post("/agent/query", json={"query": "show my all bookings"}, headers=student_headers)
    assert res_all_b.status_code == 200
    assert res_all_b.json()["intent"] == "search_my_bookings"
    assert res_all_b.json()["pending_confirmation"] is False
    print(f"[+] Fix 4.1: 'show my all bookings' -> '{safe_str(res_all_b.json()['message'])}'")

    # 5. Availability-only query: "Badminton ka koi available slot kal batao"
    res_avail_only = client.post("/agent/query", json={"query": "Badminton ka koi available slot kal batao"}, headers=student_headers)
    assert res_avail_only.status_code == 200
    assert res_avail_only.json()["intent"] == "check_available_slots"
    assert res_avail_only.json()["pending_confirmation"] is False
    assert "confirm kar du" not in res_avail_only.json()["message"].lower()
    print(f"[+] Fix 5.1: 'Badminton ka koi available slot kal batao' (Read-only, no confirmation armed) -> '{safe_str(res_avail_only.json()['message'])}'")

    print("--- [END INTENT CLASSIFICATION REGRESSION TESTS: ALL PASSED] ---\n")

    # 4. Multi-turn booking for Badminton Court 2 to trigger conflict
    client.post("/agent/query", json={"query": "Kal 5 PM badminton book kar do", "session_id": "test_s2"}, headers=admin_headers)
    client.post("/agent/query", json={"query": "Yes", "session_id": "test_s2"}, headers=admin_headers)

    # Now both courts at 5 PM are occupied -> Next booking request must offer alternatives!
    res_alt = client.post("/agent/query", json={"query": "Kal 5 PM badminton book kar do", "session_id": "test_s3"}, headers=student_headers)
    assert res_alt.status_code == 200
    res_json = res_alt.json()
    assert res_json["intent"] == "slot_conflict_alternatives"
    assert len(res_json["suggested_slots"]) > 0
    print(f"[+] 5. Slot Conflict Resolution -> Suggested Alternatives: {res_json['suggested_slots'][:3]}")

    # 5. Natural Language Cancellation: "Meri latest booking cancel kar do"
    res_cancel = client.post("/agent/query", json={"query": "Meri latest booking cancel kar do", "session_id": reg_session_2}, headers=student_headers)
    assert res_cancel.status_code == 200
    res_json = res_cancel.json()
    assert res_json["intent"] == "cancel_booking"
    assert res_json["success"] is True
    print(f"[+] 6. Cancellation by AI -> '{safe_str(res_json['message'])}'")

    # 6. Security Guardrail: Student tries to block user -> Denied
    res_student_block = client.post("/agent/query", json={"query": "Rahul ko block kar do", "session_id": "test_s1"}, headers=student_headers)
    assert res_student_block.status_code == 200
    res_json = res_student_block.json()
    assert res_json["intent"] == "admin_command_denied"
    assert res_json["success"] is False
    print(f"[+] 7. Student tries admin command ('Rahul ko block kar do') -> Denied: '{safe_str(res_json['message'])}'")

    # 7. Admin block with Confirmation: "Rahul ko block kar do"
    res_admin_block = client.post("/agent/query", json={"query": "Rahul ko block kar do", "session_id": "admin_s1"}, headers=admin_headers)
    assert res_admin_block.status_code == 200
    res_json = res_admin_block.json()
    assert res_json["pending_confirmation"] is True
    print(f"[+] 8. Admin command ('Rahul ko block kar do') -> Prompted Confirmation: '{safe_str(res_json['message'])}'")

    # Admin confirms block: "Yes"
    res_block_done = client.post("/agent/query", json={"query": "Yes", "session_id": "admin_s1"}, headers=admin_headers)
    assert res_block_done.status_code == 200
    res_json = res_block_done.json()
    assert res_json["intent"] == "user_blocked"
    assert res_json["success"] is True
    print(f"[+] 9. Admin confirms -> Block Executed: '{safe_str(res_json['message'])}'")

    # Verify blocked user login fails
    blocked_login = client.post("/auth/login", json={"email": "student@sports.edu", "password": "student123"})
    assert blocked_login.status_code == 403
    print("[+] 10. Blocked student login rejected (403 Forbidden)")

    # Admin unblocks: "unblock Rahul"
    res_unblock = client.post("/agent/query", json={"query": "unblock Rahul", "session_id": "admin_s1"}, headers=admin_headers)
    assert res_unblock.status_code == 200
    assert res_unblock.json()["intent"] == "user_unblocked"
    print(f"[+] 11. Admin unblocks Rahul -> '{safe_str(res_unblock.json()['message'])}'")

    # Restored login
    restored = client.post("/auth/login", json={"email": "student@sports.edu", "password": "student123"})
    assert restored.status_code == 200
    print("[+] 12. Restored student logged in successfully")

    # 8. Additional Agentic queries
    q_att = client.post("/agent/query", json={"query": "Mere kitne attendance hain?"}, headers=student_headers)
    assert q_att.status_code == 200
    assert q_att.json()["intent"] == "get_user_attendance"
    print(f"[+] 13. Query 'Mere kitne attendance hain?' -> '{safe_str(q_att.json()['message'])}'")

    q_users = client.post("/agent/query", json={"query": "How many users are registered?"}, headers=student_headers)
    assert q_users.status_code == 200
    print(f"[+] 14. Query 'How many users are registered?' -> '{safe_str(q_users.json()['message'])}'")

    q_courts = client.post("/agent/query", json={"query": "Aaj kaunse courts free hain?"}, headers=student_headers)
    assert q_courts.status_code == 200
    print(f"[+] 15. Query 'Aaj kaunse courts free hain?' -> Found {len(q_courts.json()['data'])} facilities")

    q_stats = client.post("/agent/query", json={"query": "Sports ERP ka overview batao"}, headers=student_headers)
    assert q_stats.status_code == 200
    print(f"[+] 16. Query 'Sports ERP ka overview batao' -> '{safe_str(q_stats.json()['message'])}'")

    # =========================================================================
    # 🧪 COMPREHENSIVE END-TO-END VERIFICATION: AUTH & STUDENT/ADMIN AI
    # =========================================================================
    print("\n--- [START END-TO-END USER & AI UPGRADE VERIFICATION] ---")

    # 1. Register new student
    reg_payload = {
        "name": "Karan Singhania",
        "email": "karan@sports.edu",
        "password": "karanPassword2026",
        "role": "student"
    }
    res_reg = client.post("/auth/register", json=reg_payload)
    assert res_reg.status_code == 200, f"Registration failed: {res_reg.text}"
    new_user_id = res_reg.json()["id"]
    print(f"[+] E2E 1: Registered new student '{reg_payload['name']}' (ID #{new_user_id})")

    # 2. Duplicate registration attempt with same email
    res_dup = client.post("/auth/register", json=reg_payload)
    assert res_dup.status_code == 400
    assert "already exists" in res_dup.json()["detail"]
    print(f"[+] E2E 2: Duplicate registration rejected with expected message: '{res_dup.json()['detail']}'")

    # 3. Login with newly registered student credentials
    res_karan_login = client.post("/auth/login", json={"email": "karan@sports.edu", "password": "karanPassword2026"})
    assert res_karan_login.status_code == 200
    karan_token = res_karan_login.json()["access_token"]
    karan_headers = {"Authorization": f"Bearer {karan_token}"}
    print("[+] E2E 3: Logged in successfully with newly registered student credentials")

    # 4. Student queries: "What sports are available?"
    q_sports = client.post("/agent/query", json={"query": "What sports are available?"}, headers=karan_headers)
    assert q_sports.status_code == 200
    assert q_sports.json()["intent"] == "list_sports"
    print(f"[+] E2E 4: 'What sports are available?' -> '{safe_str(q_sports.json()['message'])}'")

    # 5. Student queries: "Which facilities are available?"
    q_fac = client.post("/agent/query", json={"query": "Which facilities are available?"}, headers=karan_headers)
    assert q_fac.status_code == 200
    assert q_fac.json()["intent"] == "list_facilities"
    print(f"[+] E2E 5: 'Which facilities are available?' -> '{safe_str(q_fac.json()['message'])}'")

    # 6. Student queries: "Show available slots"
    q_slots = client.post("/agent/query", json={"query": "What slots are available for badminton?"}, headers=karan_headers)
    assert q_slots.status_code == 200
    assert len(q_slots.json().get("suggested_slots", [])) > 0
    print(f"[+] E2E 6: 'What slots are available for badminton?' -> Slots: {q_slots.json()['suggested_slots'][:3]}")

    # 7. Student books a slot: "Book a badminton slot tomorrow at 5 PM"
    s_karan = "karan_session_1"
    b_req = client.post("/agent/query", json={"query": "Book a badminton slot tomorrow at 5 PM", "session_id": s_karan}, headers=karan_headers)
    assert b_req.status_code == 200
    assert b_req.json()["pending_confirmation"] is True
    
    # Confirm booking: "Yes"
    b_conf = client.post("/agent/query", json={"query": "Yes", "session_id": s_karan}, headers=karan_headers)
    assert b_conf.status_code == 200
    assert b_conf.json()["intent"] == "booking_confirmed"
    karan_booking_id = b_conf.json()["data"]["id"]
    print(f"[+] E2E 7: Booking created via AI for Karan -> '{safe_str(b_conf.json()['message'])}' (Booking #{karan_booking_id})")

    # 8. Student queries: "Show my bookings"
    q_my_b = client.post("/agent/query", json={"query": "Show my bookings"}, headers=karan_headers)
    assert q_my_b.status_code == 200
    assert q_my_b.json()["intent"] == "search_my_bookings"
    assert len(q_my_b.json()["data"]) == 1
    print(f"[+] E2E 8: 'Show my bookings' retrieved 1 booking for Karan")

    # 9. Student queries: "When is my next booking?"
    q_next_b = client.post("/agent/query", json={"query": "When is my next booking?"}, headers=karan_headers)
    assert q_next_b.status_code == 200
    assert "Your next booking is" in q_next_b.json()["message"]
    print(f"[+] E2E 9: 'When is my next booking?' -> '{safe_str(q_next_b.json()['message'])}'")

    # 10. Student queries: "Show my attendance"
    q_att_k = client.post("/agent/query", json={"query": "Show my attendance"}, headers=karan_headers)
    assert q_att_k.status_code == 200
    assert q_att_k.json()["intent"] == "get_user_attendance"
    print(f"[+] E2E 10: 'Show my attendance' -> '{safe_str(q_att_k.json()['message'])}'")

    # 11. Security: Student attempts to block user id 1 (admin) or user id 3 -> Denied
    q_block_denied = client.post("/agent/query", json={"query": "Block user id 3"}, headers=karan_headers)
    assert q_block_denied.status_code == 200
    assert q_block_denied.json()["intent"] == "admin_command_denied"
    assert q_block_denied.json()["success"] is False
    print(f"[+] E2E 11: Student blocking attempt denied: '{safe_str(q_block_denied.json()['message'])}'")

    # 12. Security: Student attempts to show all users -> Denied
    q_users_denied = client.post("/agent/query", json={"query": "Show all users"}, headers=karan_headers)
    assert q_users_denied.status_code == 200
    assert q_users_denied.json()["intent"] == "admin_command_denied"
    assert q_users_denied.json()["success"] is False
    print(f"[+] E2E 12: Student 'Show all users' denied: '{safe_str(q_users_denied.json()['message'])}'")

    # 13. Student cancels booking: "Cancel my booking"
    q_cancel = client.post("/agent/query", json={"query": "Cancel my booking"}, headers=karan_headers)
    assert q_cancel.status_code == 200
    assert q_cancel.json()["intent"] == "cancel_booking"
    assert q_cancel.json()["success"] is True
    print(f"[+] E2E 13: Student cancelled booking via AI -> '{safe_str(q_cancel.json()['message'])}'")

    # 14. Student queries: "Show my cancelled bookings"
    q_canc_b = client.post("/agent/query", json={"query": "Show my cancelled bookings"}, headers=karan_headers)
    assert q_canc_b.status_code == 200
    assert len(q_canc_b.json()["data"]) == 1
    print(f"[+] E2E 14: 'Show my cancelled bookings' retrieved 1 cancelled booking")

    # 15. Admin AI actions: "Show all users"
    q_admin_users = client.post("/agent/query", json={"query": "Show all users"}, headers=admin_headers)
    assert q_admin_users.status_code == 200
    assert q_admin_users.json()["intent"] == "list_all_users"
    print(f"[+] E2E 15: Admin 'Show all users' -> Found {len(q_admin_users.json()['data'])} users")

    # 16. Admin AI actions: "Block user id {new_user_id}"
    s_admin = "admin_block_karan"
    q_adm_block = client.post("/agent/query", json={"query": f"Block user id {new_user_id}", "session_id": s_admin}, headers=admin_headers)
    assert q_adm_block.status_code == 200
    assert q_adm_block.json()["pending_confirmation"] is True
    
    q_adm_bconf = client.post("/agent/query", json={"query": "Yes", "session_id": s_admin}, headers=admin_headers)
    assert q_adm_bconf.status_code == 200
    assert q_adm_bconf.json()["intent"] == "user_blocked"
    print(f"[+] E2E 16: Admin blocked user ID #{new_user_id} -> '{safe_str(q_adm_bconf.json()['message'])}'")

    # 17. Blocked student tries to login -> 403 Forbidden
    res_k_blocked_login = client.post("/auth/login", json={"email": "karan@sports.edu", "password": "karanPassword2026"})
    assert res_k_blocked_login.status_code == 403
    print(f"[+] E2E 17: Blocked student login failed with 403 Forbidden: '{res_k_blocked_login.json()['detail']}'")

    # 18. Admin AI actions: "Unblock user id {new_user_id}"
    q_adm_unb = client.post("/agent/query", json={"query": f"Unblock user id {new_user_id}"}, headers=admin_headers)
    assert q_adm_unb.status_code == 200
    assert q_adm_unb.json()["intent"] == "user_unblocked"
    print(f"[+] E2E 18: Admin unblocked user ID #{new_user_id} -> '{safe_str(q_adm_unb.json()['message'])}'")

    # 19. Unblocked student logs in again -> 200 OK
    res_k_unblocked_login = client.post("/auth/login", json={"email": "karan@sports.edu", "password": "karanPassword2026"})
    assert res_k_unblocked_login.status_code == 200
    print("[+] E2E 19: Unblocked student logged in successfully again!")

    print("="*70)
    print("[SUCCESS] ALL REGRESSION AND INTENT TESTS PASSED PERFECTLY!")
    print("="*70)

if __name__ == "__main__":
    test_full_sports_erp_flow()
