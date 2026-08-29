"""
tests/test_multi_agent_workflow.py
-----------------------------------
Automated tests for Multi-Agent Architecture & Planner-Executor-Reflector-Responder Engine.
Inspired by Agentic ERP (Liu et al., 2026).
"""

import pytest
from datetime import date, timedelta
from app.agents.orchestrator import SportsOrchestrator, SubtaskPlan
from app.agents.booking_agent import BookingAgent
from app.agents.availability_agent import AvailabilityAgent
from app.agents.attendance_agent import AttendanceAgent
from app.agents.analytics_agent import AnalyticsAgent
from app.agents.governance_agent import UserGovernanceAgent

def test_specialized_agents_direct_execution():
    """Verify each specialized agent handles its scoped tools."""
    student_user = {"id": 2, "name": "Rahul Sharma", "email": "student@sports.edu", "role": "student"}
    admin_user = {"id": 1, "name": "Admin User", "email": "admin@sports.edu", "role": "admin"}

    # 1. AvailabilityAgent: list_sports
    avail_agent = AvailabilityAgent()
    r_avail = avail_agent.execute("list_sports", {}, student_user)
    assert r_avail.success is True
    assert len(r_avail.data) >= 6

    # 2. BookingAgent: search_my_bookings
    book_agent = BookingAgent()
    r_book = book_agent.execute("search_my_bookings", {"filter_type": "all"}, student_user)
    assert r_book.success is True
    assert "for your account" in r_book.message

    # 3. AttendanceAgent: get_user_attendance
    att_agent = AttendanceAgent()
    r_att = att_agent.execute("get_user_attendance", {}, student_user)
    assert r_att.success is True

    # 4. AnalyticsAgent: facility_utilization
    ana_agent = AnalyticsAgent()
    r_ana = ana_agent.execute("facility_utilization", {}, admin_user)
    assert r_ana.success is True
    assert len(r_ana.data) > 0

    # 5. UserGovernanceAgent: get_all_users (Admin allowed, Student denied)
    gov_agent = UserGovernanceAgent()
    r_gov_admin = gov_agent.execute("get_all_users", {}, admin_user)
    assert r_gov_admin.success is True
    assert len(r_gov_admin.data) >= 4

    r_gov_stud = gov_agent.execute("get_all_users", {}, student_user)
    assert r_gov_stud.success is False
    assert "permission" in r_gov_stud.message.lower()

def test_two_stage_intent_router():
    """Verify router maps single and cross-functional queries to correct agents."""
    orch = SportsOrchestrator()

    # Single domain
    assert orch.route_query("Show my bookings", "student") == ["BookingAgent"]
    assert orch.route_query("Which court is most utilized?", "admin") == ["AnalyticsAgent"]
    assert orch.route_query("Show my attendance", "student") == ["AttendanceAgent"]
    assert orch.route_query("Block user 3", "admin") == ["UserGovernanceAgent"]

    # Cross-functional multi-agent query
    cross_agents = orch.route_query("Find available badminton slots and book the nearest one", "student")
    assert "AvailabilityAgent" in cross_agents
    assert "BookingAgent" in cross_agents

def test_planner_executor_reflector_responder_workflow():
    """
    Verify complete 4-stage pipeline:
    Planner decomposes query -> Executor dispatches to agents -> Reflector evaluates quality -> Responder formulates output.
    """
    orch = SportsOrchestrator()
    student_user = {"id": 2, "name": "Rahul Sharma", "email": "student@sports.edu", "role": "student"}

    res = orch.execute_workflow(
        query="Show my upcoming bookings",
        current_user=student_user,
        extracted_params={"filter_type": "upcoming"}
    )

    assert res.success is True
    assert res.intent == "search_my_bookings"
    assert len(res.agent_trace) >= 3
    assert res.reflection is not None
    assert res.reflection.is_acceptable is True
    assert res.reflection.quality_score >= 0.8

def test_reflector_catches_invalid_request():
    """Verify that Reflector detects constraint errors in the plan."""
    orch = SportsOrchestrator()
    student_user = {"id": 2, "name": "Rahul Sharma", "email": "student@sports.edu", "role": "student"}
    target_date = (date.today() + timedelta(days=2)).isoformat()

    # Attempt to book out of hours (11 PM)
    plan = [
        SubtaskPlan(
            subtask_id=1,
            agent_name="BookingAgent",
            action_name="create_booking",
            params={"sport_name": "Badminton", "booking_date": target_date, "time_slot": "23:00 - 00:00"}
        )
    ]

    exec_results = orch.execute_plan(plan, student_user)
    reflection = orch.reflect_and_evaluate("Book badminton at 11 PM", plan, exec_results, student_user)
    
    assert exec_results[0].success is False
    assert "C3_OUT_OF_OPERATING_HOURS" in exec_results[0].details.get("constraint_code", "")
    assert reflection.quality_score < 1.0
