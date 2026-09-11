import os
import sys

sys.path.insert(0, r"c:\Users\hp\Downloads\sports_erp_code")
os.environ["DB_PATH"] = "sports_erp_test.db"

from fastapi.testclient import TestClient
from main import app
from app.auth_service import create_access_token
from app.database import reset_db_for_tests, get_db_connection
from datetime import date, timedelta

reset_db_for_tests()
client = TestClient(app)

admin_token = create_access_token({"sub": "1", "email": "admin@sports.edu", "role": "admin"})
# Student is Priya (ID 3) so asking for Rahul's bookings is a clean cross-user privacy test
student_token = create_access_token({"sub": "3", "email": "priya@sports.edu", "role": "student"})

admin_headers = {"Authorization": f"Bearer {admin_token}"}
student_headers = {"Authorization": f"Bearer {student_token}"}

tomorrow = (date.today() + timedelta(days=1)).isoformat()

print("==================================================")
print("=== VERIFYING STUDENT CONVERSATIONAL QUERIES ===")
print("==================================================")

# 1. Show my bookings
r1 = client.post("/agent/query", json={"query": "Show my bookings", "session_id": "std_1"}, headers=student_headers).json()
print(f"[1] Show my bookings: intent={r1.get('intent')}, success={r1.get('success')}")
assert r1["intent"] == "search_my_bookings"

# 2. Show my upcoming bookings
r2 = client.post("/agent/query", json={"query": "Show my upcoming bookings", "session_id": "std_2"}, headers=student_headers).json()
print(f"[2] Show my upcoming bookings: intent={r2.get('intent')}, success={r2.get('success')}")
assert r2["intent"] == "search_my_bookings"

# 3. Show my attendance
r3 = client.post("/agent/query", json={"query": "Show my attendance", "session_id": "std_3"}, headers=student_headers).json()
print(f"[3] Show my attendance: intent={r3.get('intent')}, success={r3.get('success')}")
assert r3["intent"] == "get_user_attendance"

# 4. Which sports are available?
r4 = client.post("/agent/query", json={"query": "Which sports are available?", "session_id": "std_4"}, headers=student_headers).json()
print(f"[4] Which sports are available?: intent={r4.get('intent')}, success={r4.get('success')}")
assert r4["intent"] == "list_sports"

# 5. Which facility has the highest utilization?
r5 = client.post("/agent/query", json={"query": "Which facility has the highest utilization?", "session_id": "std_5"}, headers=student_headers).json()
print(f"[5] Highest utilization: intent={r5.get('intent')}, success={r5.get('success')}")
assert r5["intent"] == "highest_facility_utilization"

# 6. Which sport is most popular?
r6 = client.post("/agent/query", json={"query": "Which sport is most popular?", "session_id": "std_6"}, headers=student_headers).json()
print(f"[6] Most popular sport: intent={r6.get('intent')}, success={r6.get('success')}")
assert r6["intent"] == "sport_popularity"

# 7. What are the peak booking hours?
r7 = client.post("/agent/query", json={"query": "What are the peak booking hours?", "session_id": "std_7"}, headers=student_headers).json()
print(f"[7] Peak booking hours: intent={r7.get('intent')}, success={r7.get('success')}")
assert r7["intent"] == "peak_booking_hours"

# 8. Show advanced sports ERP analytics
r8 = client.post("/agent/query", json={"query": "Show advanced sports ERP analytics", "session_id": "std_8"}, headers=student_headers).json()
print(f"[8] Advanced analytics: intent={r8.get('intent')}, success={r8.get('success')}")
assert r8["intent"] == "advanced_analytics"

# 9. Analyze facility utilization, identify the most popular sport, and show peak booking hours.
r9 = client.post("/agent/query", json={"query": "Analyze facility utilization, identify the most popular sport, and show peak booking hours.", "session_id": "std_9"}, headers=student_headers).json()
print(f"[9] Combined analytics: intent={r9.get('intent')}, success={r9.get('success')}")
assert r9["intent"] == "combined_analytics"

# 10. Book badminton tomorrow at 5 PM -> arms confirmation
r10 = client.post("/agent/query", json={"query": "Book badminton tomorrow at 5 PM", "session_id": "std_10"}, headers=student_headers).json()
print(f"[10] Book badminton tomorrow at 5 PM: intent={r10.get('intent')}, pending={r10.get('pending_confirmation')}")
assert r10["intent"] == "confirm_booking_request"
assert r10["pending_confirmation"] is True

# Confirm booking 10
r10_conf = client.post("/agent/query", json={"query": "Yes", "session_id": "std_10"}, headers=student_headers).json()
print(f"[10.1] Confirmed booking: intent={r10_conf.get('intent')}, success={r10_conf.get('success')}")
assert r10_conf["intent"] == "booking_confirmed"
assert r10_conf["success"] is True

# 11. Conflict detection & alternatives
# Book court 2 as well so badminton 5 PM is fully booked
conn = get_db_connection()
c = conn.cursor()
c.execute("INSERT OR REPLACE INTO bookings (id, user_id, facility_id, sport_id, booking_date, time_slot, status) VALUES (77, 4, 3, 2, ?, '17:00 - 18:00', 'confirmed')", (tomorrow,))
conn.commit()
conn.close()

r11 = client.post("/agent/query", json={"query": "Book badminton tomorrow at 5 PM", "session_id": "std_11"}, headers=student_headers).json()
print(f"[11] Conflict detection: intent={r11.get('intent')}, success={r11.get('success')}, suggestions={len(r11.get('suggested_slots', []))}")
assert r11["intent"] == "slot_conflict_alternatives"
assert r11["success"] is False
assert len(r11.get("suggested_slots", [])) > 0

# 12. Cancel my booking tomorrow (Single active booking)
r12 = client.post("/agent/query", json={"query": "Cancel my booking tomorrow", "session_id": "std_12"}, headers=student_headers).json()
print(f"[12] Cancel single booking: intent={r12.get('intent')}, success={r12.get('success')}")
assert r12["intent"] == "cancel_booking"
assert r12["success"] is True

# 13 & 14. Ambiguous cancellation & option selection
conn = get_db_connection()
c = conn.cursor()
c.execute("INSERT OR REPLACE INTO bookings (id, user_id, facility_id, sport_id, booking_date, time_slot, status) VALUES (81, 3, 2, 2, ?, '06:00 - 07:00', 'confirmed')", (tomorrow,))
c.execute("INSERT OR REPLACE INTO bookings (id, user_id, facility_id, sport_id, booking_date, time_slot, status) VALUES (82, 3, 2, 2, ?, '07:00 - 08:00', 'confirmed')", (tomorrow,))
conn.commit()
conn.close()

r13 = client.post("/agent/query", json={"query": "I can't remember which badminton booking I have tomorrow. Show me my options and cancel the one I choose.", "session_id": "std_13"}, headers=student_headers).json()
print(f"[13] Ambiguous cancellation: intent={r13.get('intent')}, candidates={len(r13.get('data', {}).get('candidate_bookings', []))}")
assert r13["intent"] == "disambiguate_booking_cancellation"

r14 = client.post("/agent/query", json={"query": "Option 1", "session_id": "std_13"}, headers=student_headers).json()
print(f"[14] Choose Option 1: intent={r14.get('intent')}, success={r14.get('success')}")
assert r14["intent"] == "cancel_booking"
assert r14["success"] is True

# 15. Show Rahul's bookings (Student -> Access Denied)
r15 = client.post("/agent/query", json={"query": "Show Rahul's bookings", "session_id": "std_15"}, headers=student_headers).json()
print(f"[15] Show Rahul's bookings (Student): intent={r15.get('intent')}, success={r15.get('success')}")
assert r15["intent"] == "access_denied"
assert r15["success"] is False

# 16. Show all students' bookings (Student -> Access Denied)
r16 = client.post("/agent/query", json={"query": "Show all students' bookings", "session_id": "std_16"}, headers=student_headers).json()
print(f"[16] Show all students' bookings (Student): intent={r16.get('intent')}, success={r16.get('success')}")
assert r16["intent"] == "access_denied"
assert r16["success"] is False

# 17. Cancel booking 35 (User 3 cancels own booking or nonexistent)
conn = get_db_connection()
c = conn.cursor()
c.execute("INSERT OR REPLACE INTO bookings (id, user_id, facility_id, sport_id, booking_date, time_slot, status) VALUES (35, 3, 2, 2, ?, '16:00 - 17:00', 'confirmed')", (tomorrow,))
conn.commit()
conn.close()

r17 = client.post("/agent/query", json={"query": "Cancel booking 35", "session_id": "std_17"}, headers=student_headers).json()
print(f"[17] Cancel booking 35: intent={r17.get('intent')}, success={r17.get('success')}")
assert r17["intent"] == "cancel_booking"
assert r17["success"] is True

# 18. Cancel booking ID 35
conn = get_db_connection()
c = conn.cursor()
c.execute("INSERT OR REPLACE INTO bookings (id, user_id, facility_id, sport_id, booking_date, time_slot, status) VALUES (35, 3, 2, 2, ?, '16:00 - 17:00', 'confirmed')", (tomorrow,))
conn.commit()
conn.close()

r18 = client.post("/agent/query", json={"query": "Cancel booking ID 35", "session_id": "std_18"}, headers=student_headers).json()
print(f"[18] Cancel booking ID 35: intent={r18.get('intent')}, success={r18.get('success')}")
assert r18["intent"] == "cancel_booking"
assert r18["success"] is True

print("\n==================================================")
print("=== VERIFYING ADMIN CONVERSATIONAL QUERIES ===")
print("==================================================")

# Admin 1. How many users are registered?
a1 = client.post("/agent/query", json={"query": "How many users are registered?", "session_id": "adm_1"}, headers=admin_headers).json()
print(f"[A1] How many users are registered?: intent={a1.get('intent')}, success={a1.get('success')}")
assert a1["intent"] == "list_all_users"
assert a1["success"] is True

# Admin 2. Show Rahul's bookings
a2 = client.post("/agent/query", json={"query": "Show Rahul's bookings", "session_id": "adm_2"}, headers=admin_headers).json()
print(f"[A2] Show Rahul's bookings: intent={a2.get('intent')}, success={a2.get('success')}")
assert a2["intent"] == "admin_view_user_bookings"
assert a2["success"] is True

# Admin 3. Show all students' bookings
a3 = client.post("/agent/query", json={"query": "Show all students' bookings", "session_id": "adm_3"}, headers=admin_headers).json()
print(f"[A3] Show all students' bookings: intent={a3.get('intent')}, success={a3.get('success')}")
assert a3["intent"] == "get_all_bookings"
assert a3["success"] is True

# Admin 4. Show audit logs
a4 = client.post("/agent/query", json={"query": "Show audit logs", "session_id": "adm_4"}, headers=admin_headers).json()
print(f"[A4] Show audit logs: intent={a4.get('intent')}, success={a4.get('success')}")
assert a4["intent"] == "show_audit_logs"
assert a4["success"] is True

# Admin 5. Show me the audit logs
a5 = client.post("/agent/query", json={"query": "Show me the audit logs", "session_id": "adm_5"}, headers=admin_headers).json()
print(f"[A5] Show me the audit logs: intent={a5.get('intent')}, success={a5.get('success')}")
assert a5["intent"] == "show_audit_logs"
assert a5["success"] is True

# Admin 6. Verify provenance for audit 90
a6 = client.post("/agent/query", json={"query": "Verify provenance for audit 90", "session_id": "adm_6"}, headers=admin_headers).json()
print(f"[A6] Verify provenance for audit 90: intent={a6.get('intent')}")
assert a6["intent"] == "verify_provenance"

# Admin 7. Show advanced sports ERP analytics
a7 = client.post("/agent/query", json={"query": "Show advanced sports ERP analytics", "session_id": "adm_7"}, headers=admin_headers).json()
print(f"[A7] Show advanced sports ERP analytics: intent={a7.get('intent')}, success={a7.get('success')}")
assert a7["intent"] == "advanced_analytics"
assert a7["success"] is True

# Admin 8. Which facility has the highest utilization?
a8 = client.post("/agent/query", json={"query": "Which facility has the highest utilization?", "session_id": "adm_8"}, headers=admin_headers).json()
print(f"[A8] Highest utilization: intent={a8.get('intent')}, success={a8.get('success')}")
assert a8["intent"] == "highest_facility_utilization"

# Admin 9. Which sport is most popular?
a9 = client.post("/agent/query", json={"query": "Which sport is most popular?", "session_id": "adm_9"}, headers=admin_headers).json()
print(f"[A9] Most popular sport: intent={a9.get('intent')}, success={a9.get('success')}")
assert a9["intent"] == "sport_popularity"

# Admin 10. What are the peak booking hours?
a10 = client.post("/agent/query", json={"query": "What are the peak booking hours?", "session_id": "adm_10"}, headers=admin_headers).json()
print(f"[A10] Peak booking hours: intent={a10.get('intent')}, success={a10.get('success')}")
assert a10["intent"] == "peak_booking_hours"

# Admin 11. Run the comprehensive benchmark
a11 = client.post("/agent/query", json={"query": "Run the comprehensive benchmark", "session_id": "adm_11"}, headers=admin_headers).json()
print(f"[A11] Run comprehensive benchmark: intent={a11.get('intent')}, success={a11.get('success')}")
assert a11["intent"] == "run_comprehensive_benchmark"
assert a11["success"] is True

print("\n==================================================")
print("[SUCCESS] ALL 29 STUDENT AND ADMIN QUERIES PASSED!")
print("==================================================")
