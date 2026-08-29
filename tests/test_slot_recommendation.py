import pytest
from app.agent_tools import find_alternative_slots, check_availability
from app.sports_service import rank_slots_by_proximity, ALL_STANDARD_SLOTS
from app.query_agent import extract_time_slot, process_query

def test_proximity_ranking_algorithm():
    """Verify that available slots are sorted by proximity to the requested hour."""
    available = ["06:00 - 07:00", "07:00 - 08:00", "08:00 - 09:00", "16:00 - 17:00", "18:00 - 19:00", "19:00 - 20:00"]
    
    # Requested slot is 17:00 - 18:00 (5 PM)
    # Closest slots: 16:00 (1 hr), 18:00 (1 hr), 19:00 (2 hrs), 08:00 (9 hrs), 07:00 (10 hrs), 06:00 (11 hrs)
    ranked = rank_slots_by_proximity(available, requested_slot="17:00 - 18:00")
    
    assert ranked[0] in ["16:00 - 17:00", "18:00 - 19:00"]
    assert ranked[1] in ["16:00 - 17:00", "18:00 - 19:00"]
    assert ranked[2] == "19:00 - 20:00"
    assert ranked[-1] == "06:00 - 07:00"

def test_proximity_ranking_morning_slot():
    """Verify ranking when requested slot is early morning (07:00 - 08:00)."""
    available = ["06:00 - 07:00", "08:00 - 09:00", "16:00 - 17:00", "17:00 - 18:00", "18:00 - 19:00", "19:00 - 20:00"]
    ranked = rank_slots_by_proximity(available, requested_slot="07:00 - 08:00")
    
    assert ranked[0] in ["06:00 - 07:00", "08:00 - 09:00"]
    assert ranked[1] in ["06:00 - 07:00", "08:00 - 09:00"]

def test_conflict_resolution_recommends_alternatives(client, admin_token):
    """
    Verify that when both Badminton Court 1 and Badminton Court 2 are booked at 17:00 - 18:00,
    check_availability returns available=False and provides proximity-ranked alternatives.
    """
    headers = {"Authorization": f"Bearer {admin_token}"}
    target_date = "2026-12-01"
    target_slot = "17:00 - 18:00"

    # Book Badminton Court 1 (facility_id = 2)
    client.post("/bookings", json={
        "facility_id": 2,
        "sport_id": 2,
        "booking_date": target_date,
        "time_slot": target_slot
    }, headers=headers)

    # Book Badminton Court 2 (facility_id = 3)
    client.post("/bookings", json={
        "facility_id": 3,
        "sport_id": 2,
        "booking_date": target_date,
        "time_slot": target_slot
    }, headers=headers)

    # Now both courts are booked at 17:00 - 18:00
    avail = check_availability("Badminton", target_date, target_slot)
    assert avail["available"] is False
    assert "alternative_slots" in avail
    assert len(avail["alternative_slots"]) > 0
    assert target_slot not in avail["alternative_slots"]
    # First alternative must be closest to 17:00 (i.e. 16:00 or 18:00)
    assert avail["alternative_slots"][0] in ["16:00 - 17:00", "18:00 - 19:00"]

def test_natural_language_time_parsing_exact_mapping():
    """Verify exact natural-language time slot extraction."""
    assert extract_time_slot("book badminton slot tomorrow at 9 am") == "09:00 - 10:00"
    assert extract_time_slot("book badminton tomorrow at 5 pm") == "17:00 - 18:00"
    assert extract_time_slot("tomorrow at 7 am") == "07:00 - 08:00"
    assert extract_time_slot("tomorrow at 12 pm") == "12:00 - 13:00"
    assert extract_time_slot("tomorrow at 12 am") == "00:00 - 01:00"
    assert extract_time_slot("6 pm slot") == "18:00 - 19:00"
    assert extract_time_slot("subah 9 baje") == "09:00 - 10:00"
    assert extract_time_slot("shaam 5 baje") == "17:00 - 18:00"

def test_unavailable_requested_slot_does_not_silently_reassign(client, student_token):
    """
    When user requests 9 AM (which is outside standard operating slots),
    verify system does NOT silently book 17:00 - 18:00, but reports conflict and suggests alternatives.
    """
    headers = {"Authorization": f"Bearer {student_token}"}
    resp = client.post(
        "/agent/query",
        json={"query": "book badminton on 2026-11-25 at 9 am", "session_id": "test_exact_9am_req"},
        headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "slot_conflict_alternatives"
    assert "09:00 - 10:00" in data["message"]
    assert "unavailable" in data["message"].lower()
    # Ensure suggested slots start with closest available morning slot (08:00 - 09:00)
    assert "suggested_slots" in data and len(data["suggested_slots"]) > 0
    assert data["suggested_slots"][0] == "08:00 - 09:00"

def test_available_requested_slot_preserves_exact_time(client, student_token):
    """
    When user requests 5 PM (17:00 - 18:00) on an open date, verify system arms confirmation specifically for 17:00 - 18:00.
    """
    headers = {"Authorization": f"Bearer {student_token}"}
    resp = client.post(
        "/agent/query",
        json={"query": "book badminton on 2026-11-25 at 5 pm", "session_id": "test_exact_5pm_req"},
        headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "confirm_booking_request"
    assert data["pending_confirmation"] is True
    assert "17:00 - 18:00" in data["message"]
    assert data["data"]["time_slot"] == "17:00 - 18:00"
