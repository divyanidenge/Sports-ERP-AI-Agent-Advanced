"""
app/agents/booking_agent.py
----------------------------
Booking & Reservation Specialist Agent.
Responsible for user bookings, cancellations, personal booking queries, and ownership enforcement.
"""

from typing import Dict, Any, List
from app.agents.base_agent import BaseSportsAgent, AgentExecutionResult
import app.agent_tools as tools
from app.constraint_engine import validate_booking_request, validate_cancellation_request

class BookingAgent(BaseSportsAgent):
    def __init__(self):
        super().__init__(
            name="BookingAgent",
            role_title="Sports Reservation Specialist",
            description="Manages court bookings, reservations, cancellations, and student reservation histories.",
            tool_names=["create_booking", "cancel_booking", "search_my_bookings", "get_all_bookings"]
        )

    def execute(self, subtask_name: str, params: Dict[str, Any], current_user: Dict[str, Any]) -> AgentExecutionResult:
        user_id = current_user.get("id", 0)
        user_role = current_user.get("role", "student")

        if subtask_name == "search_my_bookings":
            filter_type = params.get("filter_type", "all")
            res = tools.search_my_bookings(user_id, filter_type=filter_type)
            return AgentExecutionResult(
                agent_name=self.name,
                success=res.get("success", True),
                message=res.get("message", ""),
                data=res.get("data", [])
            )

        elif subtask_name == "create_booking":
            sport_name = params.get("sport_name", "")
            booking_date = params.get("booking_date", "")
            time_slot = params.get("time_slot", "")
            facility_id = params.get("facility_id")

            # Deterministic Constraint Validation
            c_result = validate_booking_request(
                user_id=user_id,
                sport_name=sport_name,
                booking_date=booking_date,
                time_slot=time_slot,
                facility_id=facility_id,
                user_role=user_role
            )
            if not c_result.is_valid:
                return AgentExecutionResult(
                    agent_name=self.name,
                    success=False,
                    message=f"❌ {c_result.explanation}",
                    suggested_slots=c_result.suggested_alternatives,
                    details={"constraint_code": c_result.code}
                )

            res = tools.create_booking_tool(
                user_id=user_id,
                sport_name=sport_name,
                booking_date=booking_date,
                time_slot=time_slot,
                notes=params.get("notes", "Booked via Multi-Agent System")
            )
            return AgentExecutionResult(
                agent_name=self.name,
                success=res.get("success", False),
                message=f"✅ {res.get('message', 'Booking confirmed.')}" if res.get("success") else f"⚠️ {res.get('message', 'Booking failed.')}",
                data=res.get("data"),
                action_taken="create_booking"
            )

        elif subtask_name == "cancel_booking":
            b_id = params.get("booking_id", 0)
            if b_id:
                c_val = validate_cancellation_request(booking_id=b_id, user_id=user_id, user_role=user_role)
                if not c_val.is_valid:
                    return AgentExecutionResult(
                        agent_name=self.name,
                        success=False,
                        message=f"⚠️ {c_val.explanation}",
                        details={"constraint_code": c_val.code}
                    )

            res = tools.cancel_booking_tool(
                user_id=user_id,
                role=user_role,
                sport_name=params.get("sport_name", ""),
                booking_id=b_id,
                booking_date=params.get("booking_date", ""),
                time_slot=params.get("time_slot", ""),
                target_type=params.get("target_type", "latest")
            )
            return AgentExecutionResult(
                agent_name=self.name,
                success=res.get("success", False),
                message=f"✅ {res.get('message', '')}" if res.get("success") else f"⚠️ {res.get('message', '')}",
                data=res.get("data"),
                action_taken="cancel_booking"
            )

        elif subtask_name == "get_all_bookings":
            if user_role != "admin":
                return AgentExecutionResult(
                    agent_name=self.name,
                    success=False,
                    message="You don't have permission to perform this action. Only administrators can view all campus bookings."
                )
            res = tools.get_all_bookings_tool()
            return AgentExecutionResult(
                agent_name=self.name,
                success=res.get("success", True),
                message=res.get("message", ""),
                data=res.get("data")
            )

        return AgentExecutionResult(
            agent_name=self.name,
            success=False,
            message=f"Unknown subtask '{subtask_name}' for BookingAgent."
        )
