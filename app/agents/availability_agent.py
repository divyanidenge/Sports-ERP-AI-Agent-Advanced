"""
app/agents/availability_agent.py
---------------------------------
Facility & Availability Specialist Agent.
Responsible for court availability checks, schedule queries, sports catalog, and proximity alternatives.
"""

from typing import Dict, Any, List
from app.agents.base_agent import BaseSportsAgent, AgentExecutionResult
import app.agent_tools as tools
from app.constraint_engine import validate_booking_request

class AvailabilityAgent(BaseSportsAgent):
    def __init__(self):
        super().__init__(
            name="AvailabilityAgent",
            role_title="Facility & Capacity Manager",
            description="Inspects court schedules, verifies available slots, recommends alternative slots, and lists sports/facilities.",
            tool_names=["check_availability", "find_alternative_slots", "list_sports", "list_facilities"]
        )

    def execute(self, subtask_name: str, params: Dict[str, Any], current_user: Dict[str, Any]) -> AgentExecutionResult:
        user_id = current_user.get("id", 0)
        user_role = current_user.get("role", "student")

        if subtask_name == "list_sports":
            res = tools.list_sports_tool()
            return AgentExecutionResult(
                agent_name=self.name,
                success=res.get("success", True),
                message=res.get("message", ""),
                data=res.get("data", [])
            )

        elif subtask_name == "list_facilities":
            sport_name = params.get("sport_name", "")
            res = tools.list_facilities_tool(sport_name)
            return AgentExecutionResult(
                agent_name=self.name,
                success=res.get("success", True),
                message=res.get("message", ""),
                data=res.get("data", [])
            )

        elif subtask_name == "find_alternative_slots":
            sport_name = params.get("sport_name", "")
            booking_date = params.get("booking_date", "")
            requested_slot = params.get("requested_slot")
            res = tools.find_alternative_slots(sport_name, booking_date, requested_slot=requested_slot)
            slots = res.get("available_slots", [])
            slot_str = ", ".join(slots) if slots else "No slots open"
            msg = f"Available slots for {sport_name} on {booking_date}: {slot_str}."
            return AgentExecutionResult(
                agent_name=self.name,
                success=True,
                message=msg,
                suggested_slots=slots,
                data=res
            )

        elif subtask_name == "check_availability":
            sport_name = params.get("sport_name", "")
            booking_date = params.get("booking_date", "")
            time_slot = params.get("time_slot", "")

            # Deterministic constraint verification
            c_val = validate_booking_request(
                user_id=user_id,
                sport_name=sport_name,
                booking_date=booking_date,
                time_slot=time_slot,
                user_role=user_role
            )

            if c_val.is_valid:
                fac_name = c_val.details.get("facility_name", "Court")
                msg = f"✅ {fac_name} ({sport_name}) is available on {booking_date} at {time_slot}. If you would like to book it, please say 'Yes' or 'Book it'."
                return AgentExecutionResult(
                    agent_name=self.name,
                    success=True,
                    message=msg,
                    data=c_val.details
                )
            else:
                alts = c_val.suggested_alternatives
                alt_str = f" Available alternatives are: {', '.join(alts)}." if alts else ""
                msg = f"{c_val.explanation}{alt_str} Which one would you prefer?"
                return AgentExecutionResult(
                    agent_name=self.name,
                    success=False,
                    message=msg,
                    suggested_slots=alts,
                    details={"constraint_code": c_val.code}
                )

        return AgentExecutionResult(
            agent_name=self.name,
            success=False,
            message=f"Unknown subtask '{subtask_name}' for AvailabilityAgent."
        )
