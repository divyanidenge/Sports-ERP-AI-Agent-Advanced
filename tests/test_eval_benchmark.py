"""
tests/test_eval_benchmark.py
-----------------------------
Automated tests for Function Calling vs. Text-to-SQL Empirical Benchmark (FinAI Data Assistant).
"""

import pytest
from app.eval_benchmark import (
    run_sports_erp_benchmark,
    sanitize_and_validate_sql,
    execute_sandboxed_sql,
    BENCHMARK_QUERIES
)

def test_benchmark_execution_and_metrics():
    """Verify execution of full 10-query benchmark comparing Function Calling vs Text-to-SQL."""
    report = run_sports_erp_benchmark(test_user_id=2, role="student")
    
    assert report.total_queries == 10
    assert report.function_calling_accuracy == 100.0
    assert report.function_calling_success_rate == 100.0
    assert report.function_calling_avg_latency_ms > 0
    assert report.function_calling_security_violations == 0

    assert report.text_to_sql_accuracy >= 90.0
    assert report.text_to_sql_security_violations == 0
    assert len(report.query_details) == 10

def test_sandboxed_text_to_sql_security_filter():
    """Verify sandbox rejects any DDL, mutation, or injection attempts."""
    # 1. Non-SELECT query rejected
    ok1, msg1 = sanitize_and_validate_sql("DELETE FROM bookings WHERE id = 1")
    assert ok1 is False
    assert "Security Violation" in msg1

    # 2. DROP statement rejected
    ok2, msg2 = sanitize_and_validate_sql("DROP TABLE users")
    assert ok2 is False
    assert "Security Violation" in msg2

    # 3. Multi-statement injection rejected
    ok3, msg3 = sanitize_and_validate_sql("SELECT * FROM users; DROP TABLE bookings;")
    assert ok3 is False
    assert "Security Violation" in msg3

    # 4. Valid SELECT passed
    ok4, clean4 = sanitize_and_validate_sql("SELECT id, name FROM sports WHERE id = 1")
    assert ok4 is True

def test_benchmark_api_endpoint(client, admin_token, student_token):
    """Verify GET /analytics/benchmark-evaluation enforces admin RBAC and returns structured report."""
    # Student denied (403)
    resp_s = client.get("/analytics/benchmark-evaluation", headers={"Authorization": f"Bearer {student_token}"})
    assert resp_s.status_code == 403

    # Admin allowed (200)
    resp_a = client.get("/analytics/benchmark-evaluation", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp_a.status_code == 200
    data = resp_a.json()
    assert data["total_queries"] == 10
    assert "function_calling_avg_latency_ms" in data
    assert "text_to_sql_avg_latency_ms" in data
