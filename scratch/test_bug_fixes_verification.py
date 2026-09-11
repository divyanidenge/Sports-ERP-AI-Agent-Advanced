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

student_token = create_access_token({"sub": "2", "email": "student@sports.edu", "role": "student"})
headers = {"Authorization": f"Bearer {student_token}"}
tomorrow = (date.today() + timedelta(days=1)).isoformat()

print("=== 1. MULTI-TURN CANCELLATION: EXPLICIT SPORT WITH 0 BOOKINGS ===")
# User 2 has NO badminton bookings tomorrow (only football)
conn = get_db_connection()
c = conn.cursor()
c.execute("DELETE FROM bookings WHERE user_id = 2 AND booking_date = ?", (tomorrow,))
c.execute("INSERT INTO bookings (id, user_id, facility_id, sport_id, booking_date, time_slot, status) VALUES (41, 2, 5, 4, ?, '16:00 - 17:00', 'confirmed')", (tomorrow,))
c.execute("INSERT INTO bookings (id, user_id, facility_id, sport_id, booking_date, time_slot, status) VALUES (42, 2, 5, 4, ?, '17:00 - 18:00', 'confirmed')", (tomorrow,))
conn.commit()
conn.close()

# Ask for badminton options (when user has only football)
q_badm = client.post("/agent/query", json={
    "query": "I can't remember which badminton booking I have tomorrow. Show me my options and cancel the one I choose.",
    "session_id": "test_badm_0"
}, headers=headers).json()

print("Q Badm Intent:", q_badm["intent"])
print("Q Badm Success:", q_badm["success"])
print("Q Badm Candidates:", q_badm.get("data", {}).get("candidate_bookings"))
print("Q Badm Message:", repr(q_badm.get("message")).encode('ascii', 'backslashreplace').decode('ascii'))
assert q_badm["intent"] == "cancel_booking_not_found"
assert q_badm["success"] is False
assert len(q_badm.get("data", {}).get("candidate_bookings", [])) == 0

print("\n=== 1.1 MULTI-TURN CANCELLATION: FOOTBALL OPTIONS ===")
# Ask for general cancellation tomorrow (matches the 2 football bookings)
q_ft = client.post("/agent/query", json={
    "query": "cancel tomorrow booking",
    "session_id": "test_ft_disambig"
}, headers=headers).json()

print("Q Football Intent:", q_ft["intent"])
print("Q Football Candidates:", [b["id"] for b in q_ft.get("data", {}).get("candidate_bookings", [])])
assert q_ft["intent"] == "disambiguate_booking_cancellation"
assert len(q_ft.get("data", {}).get("candidate_bookings", [])) == 2

print("\n=== 2. FOLLOW-UP WITH 'id 41' ===")
q_id41 = client.post("/agent/query", json={
    "query": "id 41",
    "session_id": "test_ft_disambig"
}, headers=headers).json()

print("Q ID 41 Intent:", q_id41["intent"])
print("Q ID 41 Success:", q_id41["success"])
print("Q ID 41 Message:", repr(q_id41.get("message")).encode('ascii', 'backslashreplace').decode('ascii'))
assert q_id41["intent"] == "cancel_booking"
assert q_id41["success"] is True

conn = get_db_connection()
c = conn.cursor()
c.execute("SELECT status FROM bookings WHERE id = 41")
assert c.fetchone()["status"] == "cancelled"
conn.close()

print("\n=== 3. RESTORE CANCELLED BOOKING: 'restore the booking id 41' ===")
q_res = client.post("/agent/query", json={
    "query": "restore the booking id 41",
    "session_id": "test_restore"
}, headers=headers).json()

print("Q Restore Intent:", q_res["intent"])
print("Q Restore Success:", q_res["success"])
print("Q Restore Message:", repr(q_res.get("message")).encode('ascii', 'backslashreplace').decode('ascii'))
assert q_res["intent"] == "restore_booking"
assert q_res["success"] is True

conn = get_db_connection()
c = conn.cursor()
c.execute("SELECT status FROM bookings WHERE id = 41")
assert c.fetchone()["status"] == "confirmed"
conn.close()

print("\n=== 4. INVALID BOOKING REQUEST VALIDATIONS ===")
# 4.1 Past date: "Book badminton on 2020-01-01"
q_past = client.post("/agent/query", json={
    "query": "Book badminton on 2020-01-01",
    "session_id": "test_past"
}, headers=headers).json()
print("Q Past Date Intent:", q_past["intent"])
print("Q Past Date Success:", q_past["success"])
print("Q Past Date Pending:", q_past.get("pending_confirmation"))
print("Q Past Date Message:", repr(q_past.get("message")).encode('ascii', 'backslashreplace').decode('ascii'))
assert q_past["intent"] == "booking_failed"
assert q_past["success"] is False
assert q_past.get("pending_confirmation") in [None, False]

# 4.2 Out of operating hours: "Book badminton tomorrow at 11 PM"
q_ooh = client.post("/agent/query", json={
    "query": "Book badminton tomorrow at 11 PM",
    "session_id": "test_ooh"
}, headers=headers).json()
print("\nQ 11 PM Intent:", q_ooh["intent"])
print("Q 11 PM Success:", q_ooh["success"])
print("Q 11 PM Pending:", q_ooh.get("pending_confirmation"))
print("Q 11 PM Suggestions:", q_ooh.get("suggested_slots"))
assert q_ooh["intent"] in ["booking_failed", "slot_conflict_alternatives"]
assert q_ooh["success"] is False
assert q_ooh.get("pending_confirmation") in [None, False]
assert len(q_ooh.get("suggested_slots", [])) > 0

print("\n[ALL 4 BUG REPRODUCTIONS AND FIXES PASSED 100%!]")
