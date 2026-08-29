import pytest
import hashlib
from app.database import hash_password, verify_password, get_db_connection

def test_password_hashing_pbkdf2_iterations():
    """Verify PBKDF2 HMAC-SHA256 password hashing with 100,000 iterations and salt."""
    pwd = "securepassword2026"
    hashed = hash_password(pwd)
    expected = hashlib.pbkdf2_hmac('sha256', pwd.encode('utf-8'), b'sports_erp_salt_2026', 100000).hex()
    assert hashed == expected
    assert verify_password(pwd, hashed) is True
    assert verify_password("wrongpwd", hashed) is False

def test_user_registration_and_duplicate_prevention(client):
    """Verify student registration and duplicate email rejection."""
    reg_data = {
        "name": "Arjun Singhal",
        "email": "arjun.unique@sports.edu",
        "password": "arjunpassword",
        "role": "student"
    }
    resp = client.post("/auth/register", json=reg_data)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "arjun.unique@sports.edu"
    assert data["role"] == "student"

    # Duplicate attempt
    dup_resp = client.post("/auth/register", json=reg_data)
    assert dup_resp.status_code == 400
    assert "already exists" in dup_resp.json()["detail"]

def test_login_invalid_credentials(client):
    """Verify rejection of non-existent user and wrong password."""
    resp_no_user = client.post("/auth/login", json={"email": "ghost@sports.edu", "password": "pass"})
    assert resp_no_user.status_code == 401
    assert "Invalid email or password" in resp_no_user.json()["detail"]

    resp_bad_pwd = client.post("/auth/login", json={"email": "student@sports.edu", "password": "wrongpassword"})
    assert resp_bad_pwd.status_code == 401
    assert "Invalid email or password" in resp_bad_pwd.json()["detail"]

def test_student_rbac_denial_on_admin_endpoints(client, student_token):
    """Verify that student tokens are rejected with HTTP 403 on admin-only endpoints."""
    headers = {"Authorization": f"Bearer {student_token}"}
    
    # 1. List all users endpoint (admin only)
    resp_users = client.get("/auth/users", headers=headers)
    assert resp_users.status_code == 403
    assert "Administrator privilege required" in resp_users.json()["detail"]

    # 2. Block user endpoint (admin only)
    resp_block = client.patch("/auth/users/2/block", headers=headers)
    assert resp_block.status_code == 403

    # 3. Advanced analytics endpoint (admin only)
    resp_analytics = client.get("/analytics/advanced", headers=headers)
    assert resp_analytics.status_code == 403

    # 4. Audit logs endpoint (admin only)
    resp_audit = client.get("/audit-logs", headers=headers)
    assert resp_audit.status_code == 403

def test_admin_access_to_admin_endpoints(client, admin_token):
    """Verify that admin tokens can access admin-only endpoints."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    resp_users = client.get("/auth/users", headers=headers)
    assert resp_users.status_code == 200
    assert len(resp_users.json()) >= 4

    resp_analytics = client.get("/analytics/advanced", headers=headers)
    assert resp_analytics.status_code == 200
    data = resp_analytics.json()
    assert "facility_utilization_rate" in data
    assert "popular_sports" in data

    resp_audit = client.get("/audit-logs", headers=headers)
    assert resp_audit.status_code == 200
    assert isinstance(resp_audit.json(), list)

def test_ownership_verified_booking_cancellation(client, student_token, admin_token):
    """Verify that student A cannot cancel student B's booking (ownership check)."""
    # Create booking for student (Rahul Sharma, user_id=2)
    s_headers = {"Authorization": f"Bearer {student_token}"}
    b_resp = client.post("/bookings", json={
        "facility_id": 1,
        "sport_id": 2,
        "booking_date": "2026-09-10",
        "time_slot": "06:00 - 07:00",
        "notes": "Rahul booking"
    }, headers=s_headers)
    assert b_resp.status_code == 200
    booking_id = b_resp.json()["id"]

    # Register student B (Pooja)
    client.post("/auth/register", json={
        "name": "Pooja Verma",
        "email": "pooja.test@sports.edu",
        "password": "poojapassword",
        "role": "student"
    })
    p_login = client.post("/auth/login", json={"email": "pooja.test@sports.edu", "password": "poojapassword"})
    p_token = p_login.json()["access_token"]
    p_headers = {"Authorization": f"Bearer {p_token}"}

    # Pooja tries to cancel Rahul's booking -> HTTP 403 Forbidden
    cancel_resp = client.delete(f"/bookings/{booking_id}", headers=p_headers)
    assert cancel_resp.status_code == 403
    assert "only cancel your own bookings" in cancel_resp.json()["detail"]

    # Admin can cancel any booking
    a_headers = {"Authorization": f"Bearer {admin_token}"}
    admin_cancel = client.delete(f"/bookings/{booking_id}", headers=a_headers)
    assert admin_cancel.status_code == 200
    assert "cancelled successfully" in admin_cancel.json()["message"]

def test_blocked_user_lockout(client, admin_token):
    """Verify that an administrator can block a user and blocked user is immediately denied login with HTTP 403."""
    a_headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Register test student
    client.post("/auth/register", json={
        "name": "Blocked Candidate",
        "email": "blocked.candidate@sports.edu",
        "password": "candidatepass",
        "role": "student"
    })
    
    # Get candidate user ID
    users = client.get("/auth/users", headers=a_headers).json()
    candidate = next(u for u in users if u["email"] == "blocked.candidate@sports.edu")
    candidate_id = candidate["id"]

    # Block user
    block_resp = client.patch(f"/auth/users/{candidate_id}/block", headers=a_headers)
    assert block_resp.status_code == 200

    # Attempt login while blocked -> 403 Forbidden
    login_resp = client.post("/auth/login", json={"email": "blocked.candidate@sports.edu", "password": "candidatepass"})
    assert login_resp.status_code == 403
    assert "Account is blocked" in login_resp.json()["detail"]

    # Unblock user
    unblock_resp = client.patch(f"/auth/users/{candidate_id}/unblock", headers=a_headers)
    assert unblock_resp.status_code == 200

    # Re-attempt login -> 200 OK
    relogin = client.post("/auth/login", json={"email": "blocked.candidate@sports.edu", "password": "candidatepass"})
    assert relogin.status_code == 200
