"""
tests/test_provenance_ledger.py
-------------------------------
Automated tests for Cryptographic Verifiable Decision Provenance Ledger.
"""

import pytest
from app.audit_service import log_audit_event
from app.provenance_engine import verify_audit_provenance
from app.database import get_db_connection

def test_provenance_token_generation_and_validity():
    """Test creating an audit event generates a valid, verifiable cryptographic token."""
    audit_id = log_audit_event(
        action="CREATE_BOOKING",
        status="SUCCESS",
        user_id=2,
        user_email="student@sports.edu",
        resource_type="booking",
        resource_id=1,
        details="Booked Badminton Court 1 for 2026-09-01 17:00-18:00"
    )
    assert audit_id is not None

    verification = verify_audit_provenance(audit_id)
    assert verification["is_valid"] is True
    assert verification["local_integrity"] is True
    assert verification["chain_intact"] is True
    assert verification["tamper_detected"] is False
    assert len(verification["stored_token"]) == 64

def test_provenance_hash_chaining():
    """Test two sequential audit events form an unbroken predecessor hash chain."""
    id1 = log_audit_event(action="TEST_ACTION_1", status="SUCCESS", user_id=1, details="Step 1")
    id2 = log_audit_event(action="TEST_ACTION_2", status="SUCCESS", user_id=1, details="Step 2")

    v1 = verify_audit_provenance(id1)
    v2 = verify_audit_provenance(id2)

    assert v1["is_valid"] is True
    assert v2["is_valid"] is True
    assert v2["prev_token"] == v1["stored_token"]

def test_audit_record_tamper_detection():
    """
    Test tampering with audit record contents is immediately detected by the verification engine.
    """
    audit_id = log_audit_event(
        action="ORIGINAL_ACTION",
        status="SUCCESS",
        user_id=2,
        details="Legitimate transaction log"
    )
    assert audit_id is not None

    # Verify initial valid state
    v_init = verify_audit_provenance(audit_id)
    assert v_init["tamper_detected"] is False

    # Simulate malicious modification directly in database table
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE audit_logs SET details = 'TAMPERED_MALICIOUS_LOG' WHERE id = ?", (audit_id,))
    conn.commit()
    conn.close()

    # Re-verify -> Must detect tamper!
    v_tampered = verify_audit_provenance(audit_id)
    assert v_tampered["tamper_detected"] is True
    assert v_tampered["local_integrity"] is False
    assert v_tampered["recomputed_token"] != v_tampered["stored_token"]

def test_verify_provenance_api_endpoint(client, admin_token, student_token):
    """Test GET /audit/verify-provenance/{audit_id} endpoint with RBAC enforcement."""
    audit_id = log_audit_event(action="API_TEST_ACTION", status="SUCCESS", user_id=1, details="Endpoint check")
    
    # 1. Admin access -> 200 OK with verification report
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get(f"/audit/verify-provenance/{audit_id}", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["audit_id"] == audit_id
    assert data["is_valid"] is True
    assert "stored_token" in data

    # 2. Student access -> 403 Forbidden
    student_headers = {"Authorization": f"Bearer {student_token}"}
    res_student = client.get(f"/audit/verify-provenance/{audit_id}", headers=student_headers)
    assert res_student.status_code == 403
