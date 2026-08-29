"""
tests/test_constraint_engine.py
--------------------------------
Automated tests for the deterministic SportsConstraintEngine (TRACE-CS).
"""

import pytest
from datetime import date, timedelta
from app.constraint_engine import (
    validate_booking_request,
    validate_cancellation_request,
    MAX_ACTIVE_BOOKINGS_PER_STUDENT,
    MAX_ADVANCE_BOOKING_DAYS
)
from app.models import BookingCreate
import app.sports_service as sports_service

def test_operating_hours_constraint():
    """C3: Rejects out-of-hours booking (e.g. 10 PM) and explains campus operating schedule."""
    res = validate_booking_request(
        user_id=2,
        sport_name="Badminton",
        booking_date="2026-11-20",
        time_slot="22:00 - 23:00",
        user_role="student"
    )
    assert res.is_valid is False
    assert res.code == "C3_OUT_OF_OPERATING_HOURS"
    assert "outside campus facility operating hours" in res.explanation
    assert len(res.suggested_alternatives) > 0

def test_past_date_constraint():
    """C4: Rejects past booking dates with clear explanation."""
    past_date = (date.today() - timedelta(days=5)).isoformat()
    res = validate_booking_request(
        user_id=2,
        sport_name="Badminton",
        booking_date=past_date,
        time_slot="17:00 - 18:00",
        user_role="student"
    )
    assert res.is_valid is False
    assert res.code == "C4_PAST_DATE"
    assert "Cannot book for past date" in res.explanation

def test_advance_booking_window_constraint():
    """C4: Rejects booking beyond 90-day reservation window."""
    far_future_date = (date.today() + timedelta(days=120)).isoformat()
    res = validate_booking_request(
        user_id=2,
        sport_name="Badminton",
        booking_date=far_future_date,
        time_slot="17:00 - 18:00",
        user_role="student"
    )
    assert res.is_valid is False
    assert res.code == "C4_ADVANCE_LIMIT_EXCEEDED"
    assert f"exceeds the maximum advance reservation window of {MAX_ADVANCE_BOOKING_DAYS} days" in res.explanation

def test_blocked_user_constraint(client, admin_token):
    """C6: Rejects booking for blocked user accounts."""
    # User 4 (Amit Verma)
    client.post("/auth/users/4/block", headers={"Authorization": f"Bearer {admin_token}"})
    
    res = validate_booking_request(
        user_id=4,
        sport_name="Badminton",
        booking_date="2026-11-20",
        time_slot="17:00 - 18:00",
        user_role="student"
    )
    assert res.is_valid is False
    assert res.code == "C6_USER_BLOCKED"
    assert "blocked" in res.explanation.lower()

    # Unblock
    client.post("/auth/users/4/unblock", headers={"Authorization": f"Bearer {admin_token}"})

def test_sport_facility_compatibility_constraint():
    """C2: Rejects booking when facility sport does not match requested sport."""
    # Facility 1 is Cricket Ground A (sport_id=1). Request Badminton (sport_id=2) on Facility 1
    res = validate_booking_request(
        user_id=2,
        sport_name="Badminton",
        booking_date="2026-11-20",
        time_slot="17:00 - 18:00",
        facility_id=1,
        user_role="student"
    )
    assert res.is_valid is False
    assert res.code == "C2_SPORT_INCOMPATIBLE"
    assert "designated for a different sport" in res.explanation

def test_student_booking_quota_constraint(client):
    """C7: Rejects booking when student reaches max quota of 10 active advance bookings."""
    # Register a new student for quota testing
    reg_resp = client.post("/auth/register", json={
        "name": "Quota Test Student",
        "email": "quotatest@sports.edu",
        "password": "password123",
        "role": "student"
    })
    assert reg_resp.status_code == 200
    student_id = reg_resp.json()["id"]
    target_date_1 = (date.today() + timedelta(days=3)).isoformat()
    target_date_2 = (date.today() + timedelta(days=4)).isoformat()
    
    # Create 10 active advance bookings
    slots = ["06:00 - 07:00", "07:00 - 08:00", "08:00 - 09:00", "16:00 - 17:00", "17:00 - 18:00"]
    created_ids = []
    for sl in slots:
        b1 = sports_service.create_booking(student_id, BookingCreate(facility_id=2, sport_id=2, booking_date=target_date_1, time_slot=sl))
        b2 = sports_service.create_booking(student_id, BookingCreate(facility_id=2, sport_id=2, booking_date=target_date_2, time_slot=sl))
        created_ids.extend([b1.id, b2.id])

    # Attempt 11th booking
    res = validate_booking_request(
        user_id=student_id,
        sport_name="Badminton",
        booking_date=target_date_1,
        time_slot="18:00 - 19:00",
        user_role="student"
    )
    assert res.is_valid is False
    assert res.code == "C7_QUOTA_EXCEEDED"
    assert f"maximum allowed: {MAX_ACTIVE_BOOKINGS_PER_STUDENT}" in res.explanation

    # Clean up
    for bid in created_ids:
        sports_service.cancel_booking(bid, student_id)

def test_cancellation_ownership_and_state_constraints():
    """C8: Validates cancellation ownership and state invariants."""
    # Create booking for Student 2
    b = sports_service.create_booking(2, BookingCreate(facility_id=2, sport_id=2, booking_date="2026-11-29", time_slot="17:00 - 18:00"))

    # Student 3 attempts to cancel Student 2's booking -> rejected
    res_unauth = validate_cancellation_request(booking_id=b.id, user_id=3, user_role="student")
    assert res_unauth.is_valid is False
    assert res_unauth.code == "C8_OWNERSHIP_VIOLATION"
    assert "do not own" in res_unauth.explanation.lower()

    # Student 2 cancels own booking -> validated
    res_auth = validate_cancellation_request(booking_id=b.id, user_id=2, user_role="student")
    assert res_auth.is_valid is True

    # Execute cancellation
    sports_service.cancel_booking(b.id, 2)

    # Attempt to cancel already cancelled booking -> rejected
    res_repeat = validate_cancellation_request(booking_id=b.id, user_id=2, user_role="student")
    assert res_repeat.is_valid is False
    assert res_repeat.code == "C8_ALREADY_CANCELLED"
    assert "already cancelled" in res_repeat.explanation.lower()
