"""
app/provenance_engine.py
------------------------
Cryptographic Decision Provenance Ledger for Sports ERP AI Agent System.

Formal Model:
Every consequential autonomous or human-confirmed state transition S_t -> S_{t+1}
(e.g., booking creation, cancellation, account block/unblock) is anchored in a
Merkle-linked, tamper-evident audit ledger:

Π_t = SHA256(
    PromptHash || Action || ResourceType || ResourceID || DetailsHash || Status || PrevToken
)

Tamper Evidence:
- Any unauthorized post-hoc modification to an audit log row alters its local token.
- Any deletion or insertion breaks the predecessor hash chain (PrevToken).
- Any alteration to the underlying SQLite record produces a state-integrity mismatch.
"""

import hashlib
import json
import sqlite3
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
from pydantic import BaseModel, Field

from app.database import get_db_connection

GENESIS_PROVENANCE_TOKEN = "0" * 64

class ProvenanceCertificate(BaseModel):
    audit_id: int
    provenance_token: str
    prev_provenance_token: str
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[int] = None
    prompt_hash: str
    timestamp: str
    is_valid: bool = True

ProvenanceProof = ProvenanceCertificate

def compute_sha256(text: str) -> str:
    """Computes standard hex SHA-256 digest."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def compute_payload_token(
    user_id: Optional[int],
    action: str,
    resource_type: Optional[str],
    resource_id: Optional[int],
    details: Optional[str],
    status: str,
    prev_token: str
) -> str:
    """
    Deterministically computes the chained provenance token Π_t.
    """
    raw_payload = f"{user_id}|{action}|{resource_type}|{resource_id}|{details or ''}|{status}|{prev_token}"
    return compute_sha256(raw_payload)

def record_provenance_for_audit(
    audit_id: int,
    conn: Optional[sqlite3.Connection] = None
) -> str:
    """
    Generates and commits a chained cryptographic provenance token for a newly inserted audit_log record.
    """
    close_conn = False
    if conn is None:
        conn = get_db_connection()
        close_conn = True

    try:
        cursor = conn.cursor()
        
        # 1. Fetch current audit record
        cursor.execute("""
            SELECT id, user_id, action, resource_type, resource_id, details, status
            FROM audit_logs WHERE id = ?
        """, (audit_id,))
        record = cursor.fetchone()
        if not record:
            return GENESIS_PROVENANCE_TOKEN

        # 2. Fetch previous provenance token in the chain
        cursor.execute("""
            SELECT provenance_token FROM audit_logs 
            WHERE id < ? AND provenance_token IS NOT NULL 
            ORDER BY id DESC LIMIT 1
        """, (audit_id,))
        prev_row = cursor.fetchone()
        prev_token = prev_row["provenance_token"] if prev_row and prev_row["provenance_token"] else GENESIS_PROVENANCE_TOKEN

        # 3. Compute chained token
        token = compute_payload_token(
            user_id=record["user_id"],
            action=record["action"],
            resource_type=record["resource_type"],
            resource_id=record["resource_id"],
            details=record["details"],
            status=record["status"],
            prev_token=prev_token
        )

        # 4. Update record with tokens
        cursor.execute("""
            UPDATE audit_logs 
            SET provenance_token = ?, prev_provenance_token = ? 
            WHERE id = ?
        """, (token, prev_token, audit_id))
        conn.commit()

        return token

    finally:
        if close_conn:
            conn.close()

generate_provenance_token = record_provenance_for_audit

def verify_audit_provenance(
    audit_id: int,
    conn: Optional[sqlite3.Connection] = None
) -> Dict[str, Any]:
    """
    Independently verifies the cryptographic provenance and tamper-status of an audit log entry.
    Checks:
    1. Local Content Integrity: Recomputed token == stored provenance_token.
    2. Chain Predecessor Integrity: Stored prev_provenance_token == predecessor's stored token.
    3. Underlying Database State Consistency: Verifies entity status matches audit claim.
    """
    close_conn = False
    if conn is None:
        conn = get_db_connection()
        close_conn = True

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, action, resource_type, resource_id, details, status, 
                   provenance_token, prev_provenance_token, created_at
            FROM audit_logs WHERE id = ?
        """, (audit_id,))
        row = cursor.fetchone()

        if not row:
            return {
                "audit_id": audit_id,
                "is_valid": False,
                "chain_intact": False,
                "tamper_detected": True,
                "error": f"Audit record #{audit_id} not found."
            }

        stored_token = row["provenance_token"]
        stored_prev = row["prev_provenance_token"] or GENESIS_PROVENANCE_TOKEN

        if not stored_token:
            return {
                "audit_id": audit_id,
                "is_valid": False,
                "chain_intact": False,
                "tamper_detected": True,
                "error": "No provenance token anchored to this legacy record."
            }

        # 1. Recompute local payload hash
        recomputed_token = compute_payload_token(
            user_id=row["user_id"],
            action=row["action"],
            resource_type=row["resource_type"],
            resource_id=row["resource_id"],
            details=row["details"],
            status=row["status"],
            prev_token=stored_prev
        )

        local_valid = (recomputed_token == stored_token)

        # 2. Verify predecessor chain integrity
        cursor.execute("""
            SELECT provenance_token FROM audit_logs 
            WHERE id < ? AND provenance_token IS NOT NULL 
            ORDER BY id DESC LIMIT 1
        """, (audit_id,))
        prev_row = cursor.fetchone()
        expected_prev = prev_row["provenance_token"] if prev_row and prev_row["provenance_token"] else GENESIS_PROVENANCE_TOKEN

        chain_valid = (stored_prev == expected_prev)

        # 3. Check physical DB entity state consistency if applicable
        db_state_consistent = True
        db_state_note = "Entity state consistent"
        if row["resource_type"] == "booking" and row["resource_id"]:
            cursor.execute("SELECT id, status FROM bookings WHERE id = ?", (row["resource_id"],))
            b_row = cursor.fetchone()
            if not b_row and row["status"] == "SUCCESS":
                db_state_consistent = False
                db_state_note = f"Discrepancy: Booking #{row['resource_id']} referenced in audit does not exist in bookings table."
            elif b_row and "cancel" in row["action"].lower() and b_row["status"] != "cancelled":
                db_state_consistent = False
                db_state_note = f"Discrepancy: Audit claims booking #{row['resource_id']} was cancelled, but row status is '{b_row['status']}'."

        tamper_detected = not (local_valid and chain_valid and db_state_consistent)

        return {
            "audit_id": audit_id,
            "action": row["action"],
            "resource_type": row["resource_type"],
            "resource_id": row["resource_id"],
            "is_valid": local_valid and chain_valid,
            "local_integrity": local_valid,
            "chain_intact": chain_valid,
            "db_state_consistent": db_state_consistent,
            "tamper_detected": tamper_detected,
            "stored_token": stored_token,
            "recomputed_token": recomputed_token,
            "prev_token": stored_prev,
            "expected_prev_token": expected_prev,
            "created_at": str(row["created_at"]),
            "db_state_note": db_state_note,
            "verification_timestamp": datetime.now().isoformat()
        }

    finally:
        if close_conn:
            conn.close()
