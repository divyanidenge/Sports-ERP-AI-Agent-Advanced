"""
tests/test_sprint_contract.py
-----------------------------
Automated tests for Adaptive Sprint Contracting & Formal Reflection.
"""

import pytest
from app.sprint_contract import (
    create_sprint_contract,
    evaluate_sprint_contract,
    SprintContract,
    ContractEvaluation
)

def test_sprint_contract_creation():
    """Test creating a sprint contract for booking intent."""
    contract = create_sprint_contract(
        goal="Book badminton tomorrow at 5 PM",
        query_type="booking",
        allowed_agents=["AvailabilityAgent", "BookingAgent"]
    )
    assert contract.contract_id.startswith("SC-")
    assert len(contract.acceptance_criteria) >= 4
    assert len(contract.expected_deliverables) >= 3
    assert "AvailabilityAgent" in contract.allowed_agents
    assert contract.rubric_weights["completeness"] == 0.30

def test_successful_execution_satisfies_contract():
    """Test successful subtask outputs achieve contract satisfaction score above threshold."""
    contract = create_sprint_contract(
        goal="Check badminton availability",
        query_type="read",
        allowed_agents=["AvailabilityAgent"]
    )
    results = [{"success": True, "message": "Badminton Court 1 is available", "data": {"available": True}}]
    
    eval_res = evaluate_sprint_contract(contract, results, constraint_status={"is_valid": True})
    assert eval_res.is_contract_satisfied is True
    assert eval_res.overall_score >= contract.threshold
    assert eval_res.replan_required is False
    assert len(eval_res.unmet_criteria) == 0

def test_failed_subtask_triggers_replan_feedback():
    """Test subtask failure results in score penalty and actionable decorrelated feedback."""
    contract = create_sprint_contract(
        goal="Cancel booking #99",
        query_type="cancellation",
        allowed_agents=["BookingAgent"]
    )
    results = [{"success": False, "message": "Error: Booking not found"}]
    
    eval_res = evaluate_sprint_contract(contract, results, constraint_status={"is_valid": False, "explanation": "Booking #99 does not exist"})
    assert eval_res.is_contract_satisfied is False
    assert eval_res.replan_required is True
    assert eval_res.overall_score < contract.threshold
    assert len(eval_res.unmet_criteria) > 0
    assert "Actionable Guidance" in eval_res.structured_feedback
