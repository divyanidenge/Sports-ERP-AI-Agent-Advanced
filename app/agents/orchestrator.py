"""
app/agents/orchestrator.py
---------------------------
Multi-Agent Orchestrator & Planner-Executor-Reflector-Responder Engine.
Inspired by Agentic ERP (Liu et al., 2026).
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, date, timedelta
from pydantic import BaseModel, Field

from app.agents.base_agent import BaseSportsAgent, AgentExecutionResult
from app.agents.booking_agent import BookingAgent
from app.agents.availability_agent import AvailabilityAgent
from app.agents.attendance_agent import AttendanceAgent
from app.agents.analytics_agent import AnalyticsAgent
from app.agents.governance_agent import UserGovernanceAgent
from app.constraint_engine import validate_booking_request
from app.sprint_contract import create_sprint_contract, evaluate_sprint_contract, SprintContract, ContractEvaluation

class SubtaskPlan(BaseModel):
    subtask_id: int
    agent_name: str
    action_name: str
    params: Dict[str, Any] = Field(default_factory=dict)
    acceptance_criterion: str = ""

class ReflectionResult(BaseModel):
    is_acceptable: bool
    quality_score: float # [0.0, 1.0]
    feedback: str = ""
    retry_recommended: bool = False
    details: Dict[str, Any] = Field(default_factory=dict)
    sprint_contract: Optional[Dict[str, Any]] = None

class OrchestrationResult(BaseModel):
    intent: str
    message: str
    success: bool
    data: Optional[Any] = None
    action_taken: Optional[str] = None
    pending_confirmation: bool = False
    suggested_slots: List[str] = Field(default_factory=list)
    agent_trace: List[Dict[str, Any]] = Field(default_factory=list)
    reflection: Optional[ReflectionResult] = None

class SportsOrchestrator:
    """
    Orchestrates specialized Sports ERP agents using:
    1. Two-Stage Intent Routing
    2. Planner -> Executor -> Reflector -> Responder Graph
    3. Deterministic Constraint Satisfaction Guardrails
    """
    def __init__(self):
        self.booking_agent = BookingAgent()
        self.availability_agent = AvailabilityAgent()
        self.attendance_agent = AttendanceAgent()
        self.analytics_agent = AnalyticsAgent()
        self.governance_agent = UserGovernanceAgent()

        self.agents: Dict[str, BaseSportsAgent] = {
            "BookingAgent": self.booking_agent,
            "AvailabilityAgent": self.availability_agent,
            "AttendanceAgent": self.attendance_agent,
            "AnalyticsAgent": self.analytics_agent,
            "UserGovernanceAgent": self.governance_agent,
        }

    def route_query(self, query: str, user_role: str) -> List[str]:
        """
        Two-stage routing algorithm:
        Stage 1: Primary agent classification
        Stage 2: Multi-agent coordination check
        """
        q = query.lower()

        # Multi-domain cross-functional queries
        if any(k in q for k in ["find", "search"]) and any(k in q for k in ["book", "reserve"]) and any(k in q for k in ["available", "slot", "nearest"]):
            return ["AvailabilityAgent", "BookingAgent"]

        # Analytics queries
        if any(k in q for k in [
            "utilization", "utilized", "utilised", "peak", "busy hours", "popularity", "popular sport", "popular",
            "cancellation statistics", "cancellation rate", "overview", "dashboard", "analytics"
        ]):
            return ["AnalyticsAgent"]

        # Attendance queries
        if any(k in q for k in ["attendance", "check in", "attended", "missed session"]):
            return ["AttendanceAgent"]

        # User Directory / Governance queries
        if any(k in q for k in ["block", "unblock", "all users", "user directory", "list users", "registered users"]):
            return ["UserGovernanceAgent"]

        # Availability queries
        if any(k in q for k in ["available", "court", "facility", "free", "khali", "slots", "sports available", "catalog"]):
            return ["AvailabilityAgent"]

        # Booking queries
        if any(k in q for k in ["book", "reserve", "cancel", "meri bookings", "my bookings", "schedule"]):
            return ["BookingAgent"]

        return ["AvailabilityAgent"] # Default specialist

    def plan_subtasks(self, query: str, active_agents: List[str], extracted_params: Dict[str, Any]) -> List[SubtaskPlan]:
        """
        Planner: Decomposes the user request into an ordered sequence of typed subtasks.
        """
        q = query.lower()
        subtasks: List[SubtaskPlan] = []

        if "AvailabilityAgent" in active_agents and "BookingAgent" in active_agents:
            # Complex Composite Query: "Find badminton availability and book nearest"
            subtasks.append(SubtaskPlan(
                subtask_id=1,
                agent_name="AvailabilityAgent",
                action_name="find_alternative_slots",
                params={
                    "sport_name": extracted_params.get("sport_name", "Badminton"),
                    "booking_date": extracted_params.get("booking_date", date.today().isoformat()),
                    "requested_slot": extracted_params.get("time_slot")
                },
                acceptance_criterion="Must return non-empty list of available time slots"
            ))
            subtasks.append(SubtaskPlan(
                subtask_id=2,
                agent_name="BookingAgent",
                action_name="check_and_arm_booking",
                params=extracted_params,
                acceptance_criterion="Must validate constraints and prepare booking confirmation"
            ))
        elif "BookingAgent" in active_agents:
            if any(k in q for k in ["cancel", "mat karo"]):
                subtasks.append(SubtaskPlan(
                    subtask_id=1,
                    agent_name="BookingAgent",
                    action_name="cancel_booking",
                    params=extracted_params,
                    acceptance_criterion="Must cancel booking with verified ownership"
                ))
            elif any(k in q for k in ["my bookings", "meri bookings", "schedule", "active", "upcoming", "cancelled"]):
                subtasks.append(SubtaskPlan(
                    subtask_id=1,
                    agent_name="BookingAgent",
                    action_name="search_my_bookings",
                    params=extracted_params,
                    acceptance_criterion="Must return only authenticated student's bookings"
                ))
            else:
                subtasks.append(SubtaskPlan(
                    subtask_id=1,
                    agent_name="BookingAgent",
                    action_name="create_booking",
                    params=extracted_params,
                    acceptance_criterion="Must satisfy all sports business constraints"
                ))
        elif "AvailabilityAgent" in active_agents:
            if any(k in q for k in ["sports", "what sports", "catalog"]):
                subtasks.append(SubtaskPlan(
                    subtask_id=1,
                    agent_name="AvailabilityAgent",
                    action_name="list_sports",
                    params={},
                    acceptance_criterion="Must return registered campus sports catalog"
                ))
            elif any(k in q for k in ["facilities", "courts", "grounds"]):
                subtasks.append(SubtaskPlan(
                    subtask_id=1,
                    agent_name="AvailabilityAgent",
                    action_name="list_facilities",
                    params=extracted_params,
                    acceptance_criterion="Must return sports facilities list"
                ))
            else:
                subtasks.append(SubtaskPlan(
                    subtask_id=1,
                    agent_name="AvailabilityAgent",
                    action_name="check_availability",
                    params=extracted_params,
                    acceptance_criterion="Must verify facility schedule"
                ))
        elif "AttendanceAgent" in active_agents:
            if "all" in q or "campus" in q:
                subtasks.append(SubtaskPlan(
                    subtask_id=1,
                    agent_name="AttendanceAgent",
                    action_name="get_all_attendance",
                    params={},
                    acceptance_criterion="Must enforce admin RBAC check"
                ))
            else:
                subtasks.append(SubtaskPlan(
                    subtask_id=1,
                    agent_name="AttendanceAgent",
                    action_name="get_user_attendance",
                    params=extracted_params,
                    acceptance_criterion="Must compute accurate attendance percentage"
                ))
        elif "AnalyticsAgent" in active_agents:
            action = "advanced_analytics"
            if "utilization" in q:
                action = "facility_utilization"
            elif "peak" in q or "busy" in q:
                action = "peak_booking_hours"
            elif "popularity" in q or "popular" in q:
                action = "sport_popularity"
            elif "cancellation" in q:
                action = "cancellation_statistics"
            elif "overview" in q or "dashboard" in q:
                action = "get_dashboard_stats"

            subtasks.append(SubtaskPlan(
                subtask_id=1,
                agent_name="AnalyticsAgent",
                action_name=action,
                params=extracted_params,
                acceptance_criterion="Must provide accurate analytical breakdown"
            ))
        elif "UserGovernanceAgent" in active_agents:
            if "block" in q and "unblock" not in q:
                subtasks.append(SubtaskPlan(
                    subtask_id=1,
                    agent_name="UserGovernanceAgent",
                    action_name="block_user",
                    params=extracted_params,
                    acceptance_criterion="Must enforce admin RBAC and block user"
                ))
            elif "unblock" in q:
                subtasks.append(SubtaskPlan(
                    subtask_id=1,
                    agent_name="UserGovernanceAgent",
                    action_name="unblock_user",
                    params=extracted_params,
                    acceptance_criterion="Must enforce admin RBAC and unblock user"
                ))
            else:
                subtasks.append(SubtaskPlan(
                    subtask_id=1,
                    agent_name="UserGovernanceAgent",
                    action_name="get_all_users",
                    params={},
                    acceptance_criterion="Must enforce admin RBAC for user directory"
                ))

        return subtasks

    def execute_plan(self, plan: List[SubtaskPlan], current_user: Dict[str, Any]) -> List[AgentExecutionResult]:
        """
        Executor: Dispatches subtasks to owning specialist agents.
        """
        results: List[AgentExecutionResult] = []
        for task in plan:
            agent = self.agents.get(task.agent_name)
            if agent:
                res = agent.execute(task.action_name, task.params, current_user)
                results.append(res)
        return results

    def reflect_and_evaluate(
        self,
        query: str,
        plan: List[SubtaskPlan],
        results: List[AgentExecutionResult],
        current_user: Dict[str, Any],
        contract: Optional[SprintContract] = None
    ) -> ReflectionResult:
        """
        Reflector: Evaluates execution results against formal Sprint Contract quality rubric:
        1. Tool Execution Success & Exception Freedom (Weight 0.30)
        2. Response Completeness & Goal Coverage (Weight 0.30)
        3. Constraint & Invariant Satisfaction (Weight 0.25)
        4. Information Efficiency & Actionability (Weight 0.15)
        """
        if not results:
            return ReflectionResult(
                is_acceptable=False,
                quality_score=0.0,
                feedback="No execution results produced by specialized agents.",
                retry_recommended=True
            )

        # Evaluate against sprint contract rubric
        q_type = "booking" if "book" in query.lower() else ("cancellation" if "cancel" in query.lower() else "read")
        if contract is None:
            contract = create_sprint_contract(goal=query, query_type=q_type, allowed_agents=[t.agent_name for t in plan])

        dict_results = [r.model_dump() for r in results]
        eval_contract = evaluate_sprint_contract(contract, dict_results, tool_call_count=len(results))

        return ReflectionResult(
            is_acceptable=eval_contract.is_contract_satisfied,
            quality_score=eval_contract.overall_score,
            feedback=eval_contract.structured_feedback or "Execution satisfies acceptance criteria and constraint rules.",
            retry_recommended=eval_contract.replan_required,
            details=eval_contract.details,
            sprint_contract=contract.model_dump()
        )

    def execute_workflow(
        self,
        query: str,
        current_user: Dict[str, Any],
        extracted_params: Dict[str, Any],
        max_iterations: int = 1
    ) -> OrchestrationResult:
        """
        Full Planner -> Executor -> Reflector -> Responder pipeline with bounded replanning (K <= 1)
        and Sprint Contracting.
        """
        active_agents = self.route_query(query, current_user.get("role", "student"))
        trace = []

        q_type = "booking" if "book" in query.lower() else ("cancellation" if "cancel" in query.lower() else "read")
        contract = create_sprint_contract(goal=query, query_type=q_type, allowed_agents=active_agents)
        trace.append({"stage": "contract_init", "contract": contract.model_dump()})

        # 1. PLAN
        plan = self.plan_subtasks(query, active_agents, extracted_params)
        trace.append({"stage": "plan", "active_agents": active_agents, "subtasks": [t.model_dump() for t in plan]})

        # 2. EXECUTE
        results = self.execute_plan(plan, current_user)
        trace.append({"stage": "execute", "results": [r.model_dump() for r in results]})

        # 3. REFLECT
        reflection = self.reflect_and_evaluate(query, plan, results, current_user, contract=contract)
        trace.append({"stage": "reflect", "reflection": reflection.model_dump()})

        # Bounded Replan on failure (K <= 1)
        if not reflection.is_acceptable and reflection.retry_recommended and max_iterations > 0:
            # Replan using fallback availability agent with contract guidance
            plan = self.plan_subtasks(query, ["AvailabilityAgent"], extracted_params)
            results = self.execute_plan(plan, current_user)
            reflection = self.reflect_and_evaluate(query, plan, results, current_user, contract=contract)
            trace.append({"stage": "replan_execute", "results": [r.model_dump() for r in results], "reflection": reflection.model_dump()})

        # 4. RESPOND
        last_res = results[-1] if results else AgentExecutionResult(agent_name="Orchestrator", success=False, message="No response.")
        
        # Determine intent name for backwards compatibility
        intent_map = {
            "search_my_bookings": "search_my_bookings",
            "create_booking": "booking_confirmed" if last_res.success else "booking_failed",
            "cancel_booking": "cancel_booking",
            "list_sports": "list_sports",
            "list_facilities": "list_facilities",
            "check_availability": "check_slot_availability" if last_res.success else "slot_conflict_alternatives",
            "find_alternative_slots": "check_available_slots",
            "get_user_attendance": "get_user_attendance",
            "get_all_attendance": "get_all_attendance",
            "facility_utilization": "facility_utilization",
            "peak_booking_hours": "peak_booking_hours",
            "sport_popularity": "sport_popularity",
            "cancellation_statistics": "cancellation_statistics",
            "get_dashboard_stats": "get_dashboard_stats",
            "advanced_analytics": "advanced_analytics",
            "get_all_users": "get_all_users",
            "block_user": "block_user",
            "unblock_user": "unblock_user"
        }

        intent = intent_map.get(plan[-1].action_name if plan else "", "general_query")
        if not last_res.success and "unavailable" in last_res.message.lower():
            intent = "slot_conflict_alternatives"

        return OrchestrationResult(
            intent=intent,
            message=last_res.message,
            success=last_res.success,
            data=last_res.data,
            action_taken=last_res.action_taken,
            pending_confirmation=last_res.pending_confirmation,
            suggested_slots=last_res.suggested_slots,
            agent_trace=trace,
            reflection=reflection
        )
