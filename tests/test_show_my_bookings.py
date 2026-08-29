import pytest
from app.query_agent import process_query
from app.models import BookingCreate
import app.sports_service as sports_service

def test_show_my_bookings_variants(client, student_token):
    """
    Verify that all phrasing variants for booking retrieval return valid structured JSON:
    - 'show my bookings'
    - 'Meri bookings dikhao'
    - 'Show my all bookings'
    - 'Do I have any upcoming bookings?'
    - 'Show my cancelled bookings'
    - 'Meri active bookings'
    """
    headers = {"Authorization": f"Bearer {student_token}"}
    
    queries = [
        ("show my bookings", "search_my_bookings"),
        ("Meri bookings dikhao", "search_my_bookings"),
        ("Show my all bookings", "search_my_bookings"),
        ("Do I have any upcoming bookings?", "search_my_bookings"),
        ("Show my cancelled bookings", "search_my_bookings"),
        ("Meri active bookings", "search_my_bookings"),
    ]

    for q_text, expected_intent in queries:
        resp = client.post("/agent/query", json={"query": q_text, "session_id": "test_booking_phrasing"}, headers=headers)
        assert resp.status_code == 200, f"Query '{q_text}' failed with HTTP {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["intent"] == expected_intent, f"Query '{q_text}' returned wrong intent: {data['intent']}"
        assert data["success"] is True
        assert "message" in data and len(data["message"]) > 0
        assert "data" in data

def test_student_booking_isolation_and_ownership(client, student_token, admin_token):
    """
    Verify that:
    1. Student A queries 'show my bookings' -> returns strictly Student A's bookings.
    2. Student B's bookings are NEVER exposed to Student A.
    3. Admin can access all campus bookings via GET /bookings?all_users=true.
    """
    # Create booking for Student A (user_id=2, student_token)
    b_data_a = BookingCreate(
        facility_id=1,
        sport_id=1,
        booking_date="2026-11-20",
        time_slot="06:00 - 07:00",
        notes="Student A Private Match"
    )
    b_res_a = sports_service.create_booking(2, b_data_a)

    # Create booking for Student B (user_id=3, Priya Patel)
    b_data_b = BookingCreate(
        facility_id=1,
        sport_id=1,
        booking_date="2026-11-21",
        time_slot="07:00 - 08:00",
        notes="Student B Private Match"
    )
    b_res_b = sports_service.create_booking(3, b_data_b)

    # 1. Student A query AI Assistant: "Show my bookings"
    resp_a = client.post(
        "/agent/query",
        json={"query": "Show my bookings", "session_id": "sess_student_a"},
        headers={"Authorization": f"Bearer {student_token}"}
    )
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    bookings_a = data_a["data"]
    # Verify all returned bookings belong to user_id=2
    for b in bookings_a:
        assert b["user_id"] == 2, f"Student A saw booking belonging to user {b['user_id']}!"
    assert any(b["id"] == b_res_a.id for b in bookings_a)
    assert not any(b["id"] == b_res_b.id for b in bookings_a), "Student A saw Student B's booking!"

    # 2. Login as Student B (Priya)
    login_b = client.post("/auth/login", json={"email": "priya@sports.edu", "password": "priya123"})
    assert login_b.status_code == 200
    token_b = login_b.json()["access_token"]

    resp_b = client.post(
        "/agent/query",
        json={"query": "Meri bookings dikhao", "session_id": "sess_student_b"},
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    bookings_b = data_b["data"]
    # Verify all returned bookings belong to user_id=3
    for b in bookings_b:
        assert b["user_id"] == 3, f"Student B saw booking belonging to user {b['user_id']}!"
    assert any(b["id"] == b_res_b.id for b in bookings_b)
    assert not any(b["id"] == b_res_a.id for b in bookings_b), "Student B saw Student A's booking!"

    # 3. Admin can access all campus bookings
    resp_admin = client.get("/bookings?all_users=true", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp_admin.status_code == 200
    all_campus_bookings = resp_admin.json()
    assert any(b["id"] == b_res_a.id for b in all_campus_bookings)
    assert any(b["id"] == b_res_b.id for b in all_campus_bookings)

    # Clean up test bookings
    sports_service.cancel_booking(b_res_a.id, 2)
    sports_service.cancel_booking(b_res_b.id, 3)
