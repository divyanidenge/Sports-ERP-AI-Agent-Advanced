"""
app/sprint_contract.py
----------------------
Adaptive Sprint Contract & Formal Reflection Engine.
Inspired by Agentic ERP (Liu et al., 2026).

Formal Model:
A Sprint Contract C = (Goal, A_crit, D_exp, G_rubric, T_out) is created by the Planner
prior to subtask execution. The Reflector scores the execution outputs against the
contract using a multi-attribute weighted rubric:

S(y) = w_comp * s_comp + w_acc * s_acc + w_cons * s_cons + w_eff * s_eff

If S(y) < θ_accept (0.75), the Reflector injects decorrelated structural feedback
into at most ONE bounded replan cycle (K ≤ 1), preventing speculative infinite loops.
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import uuid

class SprintContract(BaseModel):
    contract_id: str = Field(default_factory=lambda: f"SC-{uuid.uuid4().hex[:8].upper()}")
    goal: str
    query_type: str                         # 'read', 'booking', 'cancellation', 'governance', 'analytics'
    acceptance_criteria: List[str] = Field(default_factory=list)
    expected_deliverables: List[str] = Field(default_factory=list)
    allowed_agents: List[str] = Field(default_factory=list)
    timeout_seconds: int = 10
    rubric_weights: Dict[str, float] = Field(default_factory=lambda: {
        "completeness": 0.30,
        "accuracy": 0.30,
        "constraint_satisfaction": 0.25,
        "efficiency": 0.15
    })
    threshold: float = 0.75

class ContractEvaluation(BaseModel):
    is_contract_satisfied: bool
    overall_score: float # [0.0, 1.0]
    completeness_score: float
    accuracy_score: float
    constraint_score: float
    efficiency_score: float
    replan_required: bool
    replan_count: int = 0
    structured_feedback: str = ""
    unmet_criteria: List[str] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)

def create_sprint_contract(
    goal: str,
    query_type: str,
    allowed_agents: List[str],
    custom_criteria: Optional[List[str]] = None
) -> SprintContract:
    """
    Creates an explicit Sprint Contract defining acceptance criteria and expected deliverables.
    """
    base_criteria = []
    deliverables = []

    if query_type == "booking":
        base_criteria = [
            "Valid sport entity recognized in campus catalog",
            "Operating hours compliance (06:00-09:00, 16:00-20:00)",
            "Slot availability verified with zero conflicts",
            "Student quota margin verified (<= 10 active bookings)",
            "Protected confirmation armed before database commit"
        ]
        deliverables = ["facility_id", "booking_date", "time_slot", "confirmation_status"]

    elif query_type == "cancellation":
        base_criteria = [
            "Booking ID or date/slot unambiguously identified",
            "Student ownership or admin authorization verified",
            "Clean cancellation transition in database"
        ]
        deliverables = ["target_booking_id", "cancellation_status"]

    elif query_type == "governance":
        base_criteria = [
            "Admin role authorization verified (HTTP 403 prevention)",
            "Target user identified unambiguously",
            "Block/Unblock state transition confirmed"
        ]
        deliverables = ["target_user_id", "governance_action", "execution_status"]

    else:
        # Read / Analytics / Availability
        base_criteria = [
            "Query intent answered with grounded database facts",
            "Zero hallucinated statistics or facilities"
        ]
        deliverables = ["data_payload", "response_message"]

    if custom_criteria:
        base_criteria.extend(custom_criteria)

    return SprintContract(
        goal=goal,
        query_type=query_type,
        acceptance_criteria=base_criteria,
        expected_deliverables=deliverables,
        allowed_agents=allowed_agents
    )

def evaluate_sprint_contract(
    contract: SprintContract,
    execution_results: List[Dict[str, Any]],
    constraint_status: Optional[Dict[str, Any]] = None,
    tool_call_count: int = 1
) -> ContractEvaluation:
    """
    Evaluates actual agent execution traces against the formal Sprint Contract.
    """
    unmet = []
    
    # 1. Completeness: Did all planned subtasks return success?
    if not execution_results:
        s_comp = 0.0
        unmet.append("Zero subtask execution results produced")
    else:
        success_count = sum(1 for r in execution_results if r.get("success", False))
        s_comp = success_count / len(execution_results)
        if s_comp < 1.0:
            unmet.append(f"Subtask failure: {len(execution_results) - success_count} subtasks failed")

    # 2. Accuracy: Was requested intent correctly addressed without exceptions?
    has_errors = any("error" in str(r.get("message", "")).lower() or "fail" in str(r.get("message", "")).lower() for r in execution_results)
    s_acc = 0.50 if has_errors else 1.0

    # 3. Constraint Satisfaction
    if constraint_status is not None:
        s_cons = 1.0 if constraint_status.get("is_valid", True) else 0.40
        if not constraint_status.get("is_valid", True):
            unmet.append(f"Constraint violation: {constraint_status.get('explanation', 'Invalid constraint')}")
    else:
        s_cons = 1.0

    # 4. Efficiency: Penalize excessive tool calls (> 3 tools for single-intent)
    s_eff = 1.0 if tool_call_count <= 2 else max(0.40, 1.0 - (tool_call_count - 2) * 0.20)

    # Weighted Overall Score S(y)
    weights = contract.rubric_weights
    overall = (
        weights["completeness"] * s_comp +
        weights["accuracy"] * s_acc +
        weights["constraint_satisfaction"] * s_cons +
        weights["efficiency"] * s_eff
    )
    overall = round(overall, 3)

    is_satisfied = (overall >= contract.threshold) and not bool(unmet)
    replan_required = not is_satisfied

    # Generate Decorrelated Feedback if unsatisfied
    structured_feedback = ""
    if replan_required:
        structured_feedback = (
            f"Contract '{contract.contract_id}' evaluation scored {overall:.2f} (Threshold: {contract.threshold}).\n"
            f"Unmet Criteria:\n- " + "\n- ".join(unmet) + "\n"
            f"Actionable Guidance: Adjust parameters or route to alternative availability lookup before committing write."
        )

    return ContractEvaluation(
        is_contract_satisfied=is_satisfied,
        overall_score=overall,
        completeness_score=s_comp,
        accuracy_score=s_acc,
        constraint_score=s_cons,
        efficiency_score=s_eff,
        replan_required=replan_required,
        structured_feedback=structured_feedback,
        unmet_criteria=unmet,
        details={
            "contract_id": contract.contract_id,
            "tool_call_count": tool_call_count,
            "threshold": contract.threshold
        }
    )

def generate_decorrelated_feedback(contract: SprintContract, evaluation: ContractEvaluation) -> str:
    """
    Generates actionable, decorrelated structural feedback for bounded replanning (K <= 1).
    """
    if evaluation.is_contract_satisfied:
        return ""
    if evaluation.structured_feedback:
        return evaluation.structured_feedback
    return (
        f"Contract '{contract.contract_id}' evaluation scored {evaluation.overall_score:.2f} (Threshold: {contract.threshold}).\n"
        f"Unmet Criteria:\n- " + "\n- ".join(evaluation.unmet_criteria) + "\n"
        f"Actionable Guidance: Adjust parameters or route to alternative availability lookup before committing write."
    )
