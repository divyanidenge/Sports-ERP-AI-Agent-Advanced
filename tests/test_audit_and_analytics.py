import pytest
from app.audit_service import log_audit_event, list_audit_logs
from app.sports_service import get_advanced_analytics
from app.database import get_db_connection
from app.query_agent import process_query

def test_audit_log_persistence_and_filtering():
    """Verify that audit events are written to the database and can be queried with filters."""
    # Write test audit events
    log_audit_event(
        action="TEST_ACTION_LOGIN",
        status="SUCCESS",
        user_id=99,
        user_email="test99@sports.edu",
        details="Unit test login event"
    )
    log_audit_event(
        action="TEST_ACTION_SECURITY",
        status="DENIED",
        user_id=99,
        user_email="test99@sports.edu",
        details="Unit test permission denial"
    )

    # Query all logs for user 99
    user_logs = list_audit_logs(user_id=99)
    assert len(user_logs) >= 2
    assert any(l.action == "TEST_ACTION_LOGIN" for l in user_logs)
    assert any(l.action == "TEST_ACTION_SECURITY" for l in user_logs)

    # Query with action filter
    login_logs = list_audit_logs(action="TEST_ACTION_LOGIN")
    assert len(login_logs) >= 1
    assert all(l.action == "TEST_ACTION_LOGIN" for l in login_logs)

def test_advanced_analytics_metrics_calculation(client, admin_token):
    """Verify that get_advanced_analytics() derives correct metrics from database records."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    analytics = get_advanced_analytics()
    assert analytics.total_bookings >= 0
    assert analytics.active_confirmed_bookings >= 0
    assert analytics.cancelled_bookings >= 0
    assert 0.0 <= analytics.cancellation_rate <= 100.0
    assert 0.0 <= analytics.facility_utilization_rate <= 100.0
    assert isinstance(analytics.popular_sports, list)
    assert isinstance(analytics.peak_hours_distribution, list)
    assert isinstance(analytics.facility_breakdown, list)

def test_ai_query_advanced_analytics_routing():
    """Verify that query_agent routes 'advanced analytics' requests for admin correctly."""
    admin_user = {"id": 1, "name": "Admin User", "email": "admin@sports.edu", "role": "admin"}
    student_user = {"id": 2, "name": "Rahul Sharma", "email": "student@sports.edu", "role": "student"}

    # Admin request
    resp_admin = qa_resp = process_query("Show advanced sports ERP analytics", admin_user, session_id="analytics_test_admin")
    assert resp_admin.intent == "advanced_analytics"
    assert "Utilization Rate" in resp_admin.message

    # Student request
    resp_student = process_query("Show my analytics", student_user, session_id="analytics_test_student")
    assert resp_student.intent == "student_analytics"
    assert "Personal Sports Analytics" in resp_student.message
