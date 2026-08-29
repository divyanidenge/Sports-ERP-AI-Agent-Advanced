import pytest
from app.query_agent import process_query

def test_facility_utilization_analytics_routing():
    """Verify facility utilization query routes to 'facility_utilization' with breakdown."""
    admin_user = {"id": 1, "name": "Admin User", "email": "admin@sports.edu", "role": "admin"}
    
    # English
    resp_en = process_query("Show facility utilization analytics", admin_user, session_id="util_test_en")
    assert resp_en.intent == "facility_utilization"
    assert resp_en.success is True
    assert "Utilization Rate" in resp_en.message
    assert resp_en.data is not None
    assert isinstance(resp_en.data, list)
    assert resp_en.intent != "get_dashboard_stats"

    # Hinglish
    resp_hi = process_query("Kaun sa court kitna use ho raha hai", admin_user, session_id="util_test_hi")
    assert resp_hi.intent == "facility_utilization"
    assert resp_hi.success is True
    assert resp_hi.intent != "get_dashboard_stats"

def test_peak_booking_hours_analytics_routing():
    """Verify peak booking hours query routes to 'peak_booking_hours' with slot distribution."""
    admin_user = {"id": 1, "name": "Admin User", "email": "admin@sports.edu", "role": "admin"}

    # English
    resp_en = process_query("Show peak booking hours", admin_user, session_id="peak_test_en")
    assert resp_en.intent == "peak_booking_hours"
    assert resp_en.success is True
    assert "Busiest Time Slot" in resp_en.message
    assert resp_en.data is not None
    assert isinstance(resp_en.data, list)
    assert resp_en.intent != "get_dashboard_stats"

    # Hinglish
    resp_hi = process_query("Kaunsa time sabse busy hai", admin_user, session_id="peak_test_hi")
    assert resp_hi.intent == "peak_booking_hours"
    assert resp_hi.success is True
    assert resp_hi.intent != "get_dashboard_stats"

def test_sport_popularity_analytics_routing():
    """Verify sport popularity query routes to 'sport_popularity' with popularity rankings."""
    admin_user = {"id": 1, "name": "Admin User", "email": "admin@sports.edu", "role": "admin"}

    # English
    resp_en = process_query("Show sport popularity", admin_user, session_id="pop_test_en")
    assert resp_en.intent == "sport_popularity"
    assert resp_en.success is True
    assert "Most Popular Sport" in resp_en.message
    assert resp_en.data is not None
    assert isinstance(resp_en.data, list)
    assert resp_en.intent != "get_dashboard_stats"

    # Hinglish
    resp_hi = process_query("Sabse popular sport kaun sa hai", admin_user, session_id="pop_test_hi")
    assert resp_hi.intent == "sport_popularity"
    assert resp_hi.success is True
    assert resp_hi.intent != "get_dashboard_stats"

def test_cancellation_statistics_routing():
    """Verify cancellation statistics query routes to 'cancellation_statistics' with metrics."""
    admin_user = {"id": 1, "name": "Admin User", "email": "admin@sports.edu", "role": "admin"}
    student_user = {"id": 2, "name": "Rahul Sharma", "email": "student@sports.edu", "role": "student"}

    # Admin query
    resp_admin = process_query("Show cancellation statistics", admin_user, session_id="canc_test_admin")
    assert resp_admin.intent == "cancellation_statistics"
    assert resp_admin.success is True
    assert "Cancellation Rate" in resp_admin.message
    assert "cancellation_rate" in resp_admin.data
    assert resp_admin.intent != "get_dashboard_stats"

    # Hinglish query
    resp_hi = process_query("Kitni bookings cancel hui", admin_user, session_id="canc_test_hi")
    assert resp_hi.intent == "cancellation_statistics"
    assert resp_hi.success is True

    # Student personal cancellation query
    resp_student = process_query("Show cancellation statistics", student_user, session_id="canc_test_student")
    assert resp_student.intent == "cancellation_statistics"
    assert resp_student.success is True
    assert "Personal Cancellation" in resp_student.message
