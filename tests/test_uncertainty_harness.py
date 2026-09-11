"""
tests/test_uncertainty_harness.py
---------------------------------
Automated tests for Dynamic Epistemic Uncertainty & Confidence Harness.
"""

import pytest
from datetime import date, timedelta
from app.uncertainty_harness import evaluate_uncertainty, UncertaintyTier
from app.models import BookingCreate
import app.sports_service as sports_service

def test_low_risk_read_query_confidence():
    """Test read-only lookup receives high confidence score and LOW_RISK tier."""
    res = evaluate_uncertainty(
        query="What sports are available?",
        user_id=2,
        user_role="student"
    )
    assert res.tier == UncertaintyTier.LOW_RISK_AUTO_EXECUTE
    assert res.confidence_score >= 0.80
    assert res.action_type == "read"
    assert res.recommended_action == "execute"

def test_high_risk_consequential_booking_action():
    """Test booking intent receives HIGH_RISK tier requiring confirmation."""
    res = evaluate_uncertainty(
        query="Book badminton tomorrow at 5 PM",
        user_id=2,
        user_role="student",
        detected_params={"sport_name": "Badminton", "booking_date": "2026-09-01", "time_slot": "17:00 - 18:00"}
    )
    assert res.tier == UncertaintyTier.HIGH_RISK_CONFIRMATION
    assert res.action_type == "booking"
    assert res.recommended_action == "confirm"

def test_ambiguous_cancellation_triggers_disambiguation():
    """
    Test: Student holds 2 active bookings tomorrow.
    Query: 'Cancel my booking tomorrow'
    Outcome: Uncertainty harness detects multiple candidates, assigns MEDIUM_RISK_DISAMBIGUATION,
    and returns a structured disambiguation list.
    """
    target_date = (date.today() + timedelta(days=4)).isoformat()

    # Create 2 bookings for student 2 on same day
    b1 = sports_service.create_booking(2, BookingCreate(facility_id=2, sport_id=2, booking_date=target_date, time_slot="06:00 - 07:00"))
    b2 = sports_service.create_booking(2, BookingCreate(facility_id=2, sport_id=2, booking_date=target_date, time_slot="08:00 - 09:00"))

    res = evaluate_uncertainty(
        query="Cancel my booking tomorrow",
        user_id=2,
        user_role="student",
        detected_params={"booking_date": target_date}
    )

    assert res.tier == UncertaintyTier.MEDIUM_RISK_DISAMBIGUATION
    assert res.ambiguity_detected is True
    assert res.recommended_action == "disambiguate"
    assert res.disambiguation_prompt is not None
    assert "active bookings" in res.disambiguation_prompt
    assert len(res.candidate_options) >= 2

    # Clean up
    sports_service.cancel_booking(b1.id, 2)
    sports_service.cancel_booking(b2.id, 2)

def test_specific_id_cancellation_bypasses_disambiguation():
    """Test specific booking ID cancellation is unambiguous and routes directly to confirmation."""
    res = evaluate_uncertainty(
        query="Cancel booking #10",
        user_id=2,
        user_role="student"
    )
    assert res.ambiguity_detected is False
    assert res.tier == UncertaintyTier.HIGH_RISK_CONFIRMATION
    assert res.recommended_action == "confirm"
