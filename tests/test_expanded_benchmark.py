"""
tests/test_expanded_benchmark.py
--------------------------------
Automated tests for 30-scenario Four-Paradigm Empirical Benchmark Suite.
"""

import pytest
from app.expanded_benchmark import run_expanded_benchmark, sanitize_text_to_sql, EXPANDED_BENCHMARK_SCENARIOS

def test_expanded_benchmark_30_scenarios_structure():
    """Verify exactly 30 scenarios exist spanning 3 tiers."""
    assert len(EXPANDED_BENCHMARK_SCENARIOS) == 30
    tiers = {sc["tier"] for sc in EXPANDED_BENCHMARK_SCENARIOS}
    assert len(tiers) == 3
    assert "Tier 1: Analytical" in tiers
    assert "Tier 2: Transactional" in tiers
    assert "Tier 3: Multi-Agent / Conflict" in tiers

def test_expanded_benchmark_execution():
    """Run full benchmark execution and verify generated metrics summary."""
    report = run_expanded_benchmark(test_user_id=1, role="admin")
    assert report["total_scenarios_evaluated"] == 30
    assert len(report["paradigms_compared"]) == 4

    metrics = report["summary_metrics"]
    assert "proposed_hybrid" in metrics
    assert "text_to_sql" in metrics
    assert "monolithic_fc" in metrics
    assert "react_baseline" in metrics

    # Verify proposed hybrid achieves superior TCR without constraint violations
    prop = metrics["proposed_hybrid"]
    assert prop["task_completion_rate_pct"] >= 90.0
    assert prop["constraint_violation_rate_pct"] == 0.0
    assert prop["safety_violations"] == 0

    # Statistical comparison present
    assert "proposed_vs_text_to_sql" in report["statistical_tests"]

def test_sql_sandbox_interceptor():
    """Test text-to-sql sandbox rejects destructive DDL/DML injections."""
    safe, msg = sanitize_text_to_sql("SELECT id, name FROM sports")
    assert safe is True

    unsafe_insert, msg1 = sanitize_text_to_sql("INSERT INTO users (name) VALUES ('Hacker')")
    assert unsafe_insert is False
    assert "Security Sandbox Intercepted" in msg1

    unsafe_drop, msg2 = sanitize_text_to_sql("DROP TABLE bookings")
    assert unsafe_drop is False
    assert "Security Sandbox Intercepted" in msg2

def test_comprehensive_benchmark_api_endpoint(client, admin_token, student_token):
    """Test GET /analytics/comprehensive-benchmark endpoint with RBAC."""
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    res_admin = client.get("/analytics/comprehensive-benchmark", headers=admin_headers)
    assert res_admin.status_code == 200
    data = res_admin.json()
    assert data["total_scenarios_evaluated"] == 30
    assert "summary_metrics" in data

    student_headers = {"Authorization": f"Bearer {student_token}"}
    res_student = client.get("/analytics/comprehensive-benchmark", headers=student_headers)
    assert res_student.status_code == 403
