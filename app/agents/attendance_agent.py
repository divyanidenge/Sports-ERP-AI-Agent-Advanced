"""
app/agents/attendance_agent.py
-------------------------------
Attendance & Session Tracking Specialist Agent.
Responsible for student check-ins, attendance rates, session records, and admin attendance tracking.
"""

from typing import Dict, Any
from app.agents.base_agent import BaseSportsAgent, AgentExecutionResult
import app.agent_tools as tools

class AttendanceAgent(BaseSportsAgent):
    def __init__(self):
        super().__init__(
            name="AttendanceAgent",
            role_title="Attendance & Check-in Coordinator",
            description="Manages student attendance tracking, session records, attendance rates, and check-in verifications.",
            tool_names=["get_user_attendance", "get_all_attendance", "mark_attendance"]
        )

    def execute(self, subtask_name: str, params: Dict[str, Any], current_user: Dict[str, Any]) -> AgentExecutionResult:
        user_id = current_user.get("id", 0)
        user_role = current_user.get("role", "student")

        if subtask_name == "get_user_attendance":
            sport_name = params.get("sport_name", "")
            target_user_id = params.get("target_user_id", user_id)
            
            # Students can only view their own attendance
            if user_role != "admin" and target_user_id != user_id:
                return AgentExecutionResult(
                    agent_name=self.name,
                    success=False,
                    message="You don't have permission to view other users' attendance."
                )

            res = tools.get_user_attendance_tool(target_user_id, sport_name=sport_name)
            return AgentExecutionResult(
                agent_name=self.name,
                success=res.get("success", True),
                message=res.get("message", ""),
                data=res.get("data", [])
            )

        elif subtask_name == "get_all_attendance":
            if user_role != "admin":
                return AgentExecutionResult(
                    agent_name=self.name,
                    success=False,
                    message="You don't have permission to perform this action. Only administrators can view campus-wide attendance."
                )
            res = tools.get_all_attendance_tool()
            return AgentExecutionResult(
                agent_name=self.name,
                success=res.get("success", True),
                message=res.get("message", ""),
                data=res.get("data", [])
            )

        elif subtask_name == "mark_attendance":
            booking_id = params.get("booking_id", 0)
            status_val = params.get("status", "present")
            target_user_id = params.get("target_user_id", user_id)

            if user_role != "admin" and target_user_id != user_id:
                return AgentExecutionResult(
                    agent_name=self.name,
                    success=False,
                    message="You don't have permission to mark attendance for other users."
                )

            res = tools.mark_attendance_tool(
                booking_id=booking_id,
                user_id=target_user_id,
                status=status_val,
                marked_by=user_id
            )
            return AgentExecutionResult(
                agent_name=self.name,
                success=res.get("success", False),
                message=res.get("message", ""),
                data=res.get("data")
            )

        return AgentExecutionResult(
            agent_name=self.name,
            success=False,
            message=f"Unknown subtask '{subtask_name}' for AttendanceAgent."
        )
