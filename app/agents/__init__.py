"""
app/agents module
-----------------
Role-aligned multi-agent architecture for Sports ERP.
"""

from app.agents.base_agent import BaseSportsAgent, AgentExecutionResult
from app.agents.booking_agent import BookingAgent
from app.agents.availability_agent import AvailabilityAgent
from app.agents.attendance_agent import AttendanceAgent
from app.agents.analytics_agent import AnalyticsAgent
from app.agents.governance_agent import UserGovernanceAgent
from app.agents.orchestrator import SportsOrchestrator, OrchestrationResult, SubtaskPlan, ReflectionResult

__all__ = [
    "BaseSportsAgent",
    "AgentExecutionResult",
    "BookingAgent",
    "AvailabilityAgent",
    "AttendanceAgent",
    "AnalyticsAgent",
    "UserGovernanceAgent",
    "SportsOrchestrator",
    "OrchestrationResult",
    "SubtaskPlan",
    "ReflectionResult"
]
