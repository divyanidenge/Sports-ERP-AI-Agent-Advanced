import sqlite3
from typing import Optional, List, Dict, Any
from app.database import get_db_connection
from app.models import AuditLogResponse

def log_audit_event(
    action: str,
    status: str = "SUCCESS",
    user_id: Optional[int] = None,
    user_email: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None
) -> Optional[int]:
    """Persist a structured audit trail event into the SQLite audit_logs table."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO audit_logs (
                user_id, user_email, action, resource_type, resource_id, details, status, ip_address
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            user_email,
            action,
            resource_type,
            resource_id,
            details,
            status,
            ip_address
        ))
        conn.commit()
        log_id = cursor.lastrowid
        
        # Anchor cryptographic chained provenance
        if log_id:
            try:
                from app.provenance_engine import record_provenance_for_audit
                record_provenance_for_audit(log_id, conn=conn)
            except Exception as pe:
                print(f"[PROVENANCE_ERROR] Failed to anchor token for audit #{log_id}: {pe}")

        return log_id
    except Exception as e:
        # Audit logging should fail gracefully without crashing primary transactional flows
        print(f"[AUDIT_ERROR] Failed to record audit log '{action}': {e}")
        return None
    finally:
        conn.close()

def list_audit_logs(
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> List[AuditLogResponse]:
    """Retrieve audit logs with optional filtering by user or action."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        query = "SELECT id, user_id, user_email, action, resource_type, resource_id, details, status, ip_address, created_at FROM audit_logs WHERE 1=1"
        params = []
        
        if user_id is not None:
            query += " AND user_id = ?"
            params.append(user_id)
        if action is not None:
            query += " AND action = ?"
            params.append(action)
            
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        return [AuditLogResponse(**dict(r)) for r in rows]
    finally:
        conn.close()
