"""
app/agents/analytics_agent.py
------------------------------
Analytics & Performance Intelligence Specialist Agent.
Responsible for facility utilization, peak booking hours, sport popularity, cancellation stats, and overview metrics.
"""

from typing import Dict, Any
from app.agents.base_agent import BaseSportsAgent, AgentExecutionResult
import app.agent_tools as tools
import app.sports_service as sports_service

class AnalyticsAgent(BaseSportsAgent):
    def __init__(self):
        super().__init__(
            name="AnalyticsAgent",
            role_title="Sports Intelligence & Analytics Director",
            description="Computes utilization metrics, peak booking intervals, sport popularity rankings, cancellation statistics, and ERP overviews.",
            tool_names=[
                "facility_utilization", "peak_booking_hours", "sport_popularity",
                "cancellation_statistics", "get_dashboard_stats", "advanced_analytics"
            ]
        )

    def execute(self, subtask_name: str, params: Dict[str, Any], current_user: Dict[str, Any]) -> AgentExecutionResult:
        user_id = current_user.get("id", 0)
        user_role = current_user.get("role", "student")

        if subtask_name == "facility_utilization":
            res = tools.get_facility_utilization_tool()
            return AgentExecutionResult(
                agent_name=self.name,
                success=res.get("success", True),
                message=res.get("message", ""),
                data=res.get("data", [])
            )

        elif subtask_name == "peak_booking_hours":
            res = tools.get_peak_booking_hours_tool()
            return AgentExecutionResult(
                agent_name=self.name,
                success=res.get("success", True),
                message=res.get("message", ""),
                data=res.get("data", [])
            )

        elif subtask_name == "sport_popularity":
            res = tools.get_sport_popularity_tool()
            return AgentExecutionResult(
                agent_name=self.name,
                success=res.get("success", True),
                message=res.get("message", ""),
                data=res.get("data", [])
            )

        elif subtask_name == "cancellation_statistics":
            res = tools.get_cancellation_statistics_tool(user_id=user_id, role=user_role)
            return AgentExecutionResult(
                agent_name=self.name,
                success=res.get("success", True),
                message=res.get("message", ""),
                data=res.get("data", {})
            )

        elif subtask_name == "get_dashboard_stats":
            res = tools.get_dashboard_stats_tool()
            return AgentExecutionResult(
                agent_name=self.name,
                success=res.get("success", True),
                message=res.get("message", ""),
                data=res.get("data", {})
            )

        elif subtask_name == "advanced_analytics":
            if user_role == "admin":
                analytics = sports_service.get_advanced_analytics()
                top_sport = analytics.popular_sports[0]["sport_name"] if analytics.popular_sports else "None"
                peak_slot = analytics.peak_hours_distribution[0]["time_slot"] if analytics.peak_hours_distribution else "None"
                msg = (
                    f"📊 **Advanced Sports ERP Analytics**:\n"
                    f"• **Total Bookings:** {analytics.total_bookings} ({analytics.active_confirmed_bookings} active, {analytics.cancelled_bookings} cancelled, {analytics.cancellation_rate}% cancellation rate)\n"
                    f"• **Facility Utilization Rate:** {analytics.facility_utilization_rate}%\n"
                    f"• **Most Popular Sport:** {top_sport}\n"
                    f"• **Peak Booking Interval:** {peak_slot}\n"
                    f"• **Attendance Present Rate:** {analytics.attendance_present_rate}%"
                )
                return AgentExecutionResult(
                    agent_name=self.name,
                    success=True,
                    message=msg,
                    data=analytics.model_dump()
                )
            else:
                att = tools.get_user_attendance_tool(user_id)
                book = tools.search_my_bookings(user_id)
                msg = f"Your Personal Sports Analytics: {book.get('active_count', 0)} active bookings, {att.get('count', 0)} total sessions attended with a {att.get('attendance_rate', 0.0)}% attendance rate."
                return AgentExecutionResult(
                    agent_name=self.name,
                    success=True,
                    message=msg,
                    data={"bookings": book, "attendance": att}
                )

        return AgentExecutionResult(
            agent_name=self.name,
            success=False,
            message=f"Unknown subtask '{subtask_name}' for AnalyticsAgent."
        )
