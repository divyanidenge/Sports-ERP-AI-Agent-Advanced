"""
tests/test_research_extensions_nl_routing.py
---------------------------------------------
End-to-End Natural Language Routing Tests for All Research Extensions & User Bug Scenarios.
"""

import pytest
from datetime import date, timedelta
from app.query_agent import process_query, extract_tournament_params

def test_nl_tournament_4_teams_round_robin():
    user = {"id": 1, "role": "student", "name": "Student 1"}
    resp = process_query("Schedule a round robin tournament for 4 teams in badminton.", user, "test_s1")
    assert resp.intent == "tournament_schedule"
    assert resp.success is True
    assert resp.data["total_matches"] == 6
    assert resp.data["is_feasible"] is True

def test_nl_tournament_20_teams_1_court_1_day_4h_rest():
    user = {"id": 1, "role": "student", "name": "Student 1"}
    resp = process_query("Schedule a tournament for 20 teams on 1 court in one day with 4 hours rest between matches.", user, "test_s2")
    assert resp.intent == "tournament_schedule"
    assert resp.success is False
    assert resp.data["total_matches"] == 190
    assert resp.data["is_feasible"] is False
    assert "Insufficient court capacity" in resp.message
    assert "190 matches required for 20 teams" in resp.message

def test_nl_tournament_8_teams_2_courts_2_days():
    user = {"id": 1, "role": "student", "name": "Student 1"}
    resp = process_query("Schedule a badminton tournament for 8 teams on 2 courts over 2 days.", user, "test_s3")
    assert resp.intent == "tournament_schedule"
    assert resp.data["total_matches"] == 28

def test_nl_predict_facility_demand_tomorrow():
    user = {"id": 1, "role": "student", "name": "Student 1"}
    resp = process_query("Predict facility demand for tomorrow.", user, "test_s4")
    assert resp.intent == "demand_forecasting"
    assert resp.success is True
    assert "Campus Facility Demand Forecast" in resp.message
    assert "highest_demand_sport" in resp.data

def test_nl_which_sports_facilities_likely_to_be_congested():
    user = {"id": 1, "role": "student", "name": "Student 1"}
    resp = process_query("Which sports facilities are likely to be congested?", user, "test_s5")
    assert resp.intent == "demand_forecasting"
    assert resp.success is True
    assert "Congested Facilities" in resp.message
    assert "congested_sports" in resp.data

def test_nl_which_facility_highest_booking_demand():
    user = {"id": 1, "role": "student", "name": "Student 1"}
    resp = process_query("Which facility will have the highest booking demand?", user, "test_s6")
    assert resp.intent == "demand_forecasting"
    assert resp.success is True
    assert "Highest Predicted Demand Facility" in resp.message
    assert "sport_name" in resp.data

def test_nl_predict_congestion_badminton_facilities():
    user = {"id": 1, "role": "student", "name": "Student 1"}
    resp = process_query("Predict congestion for badminton facilities.", user, "test_s7")
    assert resp.intent == "demand_forecasting"
    assert resp.success is True
    assert resp.data["sport_name"] == "Badminton"
    assert "predicted_occupancy_pct" in resp.data

def test_nl_predict_badminton_demand_tomorrow_6pm():
    user = {"id": 1, "role": "student", "name": "Student 1"}
    resp = process_query("Predict badminton demand tomorrow at 6 PM.", user, "test_s8")
    assert resp.intent == "demand_forecasting"
    assert resp.success is True
    assert resp.data["sport_name"] == "Badminton"
    assert resp.data["time_slot"] == "18:00 - 19:00"

def test_nl_show_my_bookings():
    user = {"id": 1, "role": "student", "name": "Student 1"}
    resp = process_query("Show my bookings.", user, "test_s9")
    assert resp.intent in ["search_my_bookings", "view_bookings", "show_my_bookings"]
    assert resp.success is True

def test_nl_what_sports_are_available():
    user = {"id": 1, "role": "student", "name": "Student 1"}
    resp = process_query("What sports are available?", user, "test_s10")
    assert resp.intent == "list_sports"
    assert resp.success is True

def test_nl_book_badminton_tomorrow_5pm():
    user = {"id": 1, "role": "student", "name": "Student 1"}
    resp = process_query("Book a badminton slot tomorrow at 5 PM.", user, "test_s11")
    assert resp.intent in ["confirm_booking_request", "booking_confirmation_required", "booking_created", "availability_checked", "booking_failed"]

def test_nl_which_facility_will_be_busiest_tomorrow():
    user = {"id": 1, "role": "student", "name": "Student 1"}
    resp = process_query("Which facility will be busiest tomorrow?", user, "test_s12")
    assert resp.intent == "demand_forecasting"
    assert resp.success is True
    assert "Highest Predicted Demand Facility" in resp.message
