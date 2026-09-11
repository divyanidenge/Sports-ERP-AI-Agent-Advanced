"""
tests/test_symbolic_mus_engine.py
---------------------------------
Automated tests for Symbolic MUS/MCS Conflict & Explanation Engine (TRACE-CS).
"""

import pytest
from datetime import date, timedelta
from app.symbolic_mus_engine import (
    evaluate_symbolic_clauses,
    extract_mus,
    solve_mcs,
    evaluate_booking_mus_mcs,
    generate_contrastive_mus_explanation
)
from app.database import get_db_connection
from app.models import BookingCreate
import app.sports_service as sports_service

def test_symbolic_satisfiable_request(client, student_token):
    """Test valid booking satisfies all 8 symbolic invariants."""
    target_date = (date.today() + timedelta(days=2)).isoformat()
    res = evaluate_booking_mus_mcs(
        user_id=2,
        sport_name="Badminton",
        booking_date=target_date,
        time_slot="07:00 - 08:00",
        user_role="student"
    )
    assert res.is_satisfiable is True
    assert len(res.violated_clauses) == 0
    assert len(res.mus) == 0
    assert "Satisfiable" in res.contrastive_explanation

def test_single_clause_violation_mus():
    """Test single violation (Operating Hours) isolates MUS of size 1."""
    target_date = (date.today() + timedelta(days=2)).isoformat()
    res = evaluate_booking_mus_mcs(
        user_id=2,
        sport_name="Badminton",
        booking_date=target_date,
        time_slot="22:00 - 23:00", # Out of hours
        user_role="student"
    )
    assert res.is_satisfiable is False
    assert len(res.mus) == 1
    assert res.mus[0].clause_id == "C3_OPERATING_HOURS"
    assert "outside campus operating hours" in res.contrastive_explanation

def test_multiple_simultaneous_violations_mus():
    """
    Test multiple simultaneous violations:
    1. Past Date (C4)
    2. Out of Operating Hours (C3)
    3. Blocked User (C6)
    Verifies that the engine detects ALL simultaneous violations in the MUS.
    """
    # Create or identify blocked user
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_blocked = 1 WHERE id = 4")
    conn.commit()
    conn.close()

    res = evaluate_booking_mus_mcs(
        user_id=4, # Blocked user
        sport_name="Badminton",
        booking_date="2020-01-01", # Past date (C4)
        time_slot="12:00 - 13:00", # Out of hours (C3)
        user_role="student"
    )
    assert res.is_satisfiable is False
    viol_ids = {c.clause_id for c in res.mus}
    assert "C4_TEMPORAL_VALIDITY" in viol_ids
    assert "C3_OPERATING_HOURS" in viol_ids
    assert "C6_ACCOUNT_STANDING" in viol_ids
    assert len(res.mus) == 3
    assert "conflicting constraints" in res.contrastive_explanation

    # Clean up blocked status
    conn = get_db_connection()
    conn.execute("UPDATE users SET is_blocked = 0 WHERE id = 4")
    conn.commit()
    conn.close()

def test_mcs_minimal_relaxation_generation(client):
    """Test that when a slot is unavailable, MCS returns proximity-ranked time slot relaxations."""
    target_date = (date.today() + timedelta(days=5)).isoformat()
    
    # Book all badminton courts at 17:00 - 18:00
    b1 = sports_service.create_booking(1, BookingCreate(facility_id=2, sport_id=2, booking_date=target_date, time_slot="17:00 - 18:00"))
    b2 = sports_service.create_booking(1, BookingCreate(facility_id=3, sport_id=2, booking_date=target_date, time_slot="17:00 - 18:00"))

    # Attempt student booking on fully occupied slot
    res = evaluate_booking_mus_mcs(
        user_id=2,
        sport_name="Badminton",
        booking_date=target_date,
        time_slot="17:00 - 18:00",
        user_role="student"
    )
    assert res.is_satisfiable is False
    assert any(c.clause_id == "C5_SLOT_AVAILABILITY" for c in res.mus)
    assert len(res.mcs_relaxations) > 0
    assert res.mcs_relaxations[0]["relaxation_type"] == "SHIFT_TIME_SLOT"
    assert len(res.suggested_alternatives) > 0
    assert "Minimal Correction Options" in res.contrastive_explanation

    # Clean up
    sports_service.cancel_booking(b1.id, 1)
    sports_service.cancel_booking(b2.id, 1)
