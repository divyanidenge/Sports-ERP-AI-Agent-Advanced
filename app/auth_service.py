from fastapi import HTTPException, status
from app.database import get_db_connection, hash_password, verify_password
from app.models import UserRegister, UserLogin, UserResponse, TokenResponse
from app.auth import create_access_token

def register_user(data: UserRegister) -> UserResponse:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if email already exists
    cursor.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (data.email.strip(),))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists. Please log in."
        )
    
    hashed_pwd = hash_password(data.password)
    cursor.execute(
        "INSERT INTO users (name, email, hashed_password, role, is_blocked) VALUES (?, ?, ?, ?, 0)",
        (data.name.strip(), data.email.strip().lower(), hashed_pwd, data.role)
    )
    conn.commit()
    user_id = cursor.lastrowid
    
    cursor.execute("SELECT id, name, email, role, is_blocked, created_at FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    return UserResponse(**dict(row))

def authenticate_user(data: UserLogin) -> TokenResponse:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT id, name, email, hashed_password, role, is_blocked, created_at FROM users WHERE LOWER(email) = LOWER(?)",
        (data.email.strip(),)
    )
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )
    
    user_dict = dict(row)
    if not verify_password(data.password, user_dict["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )
    
    if user_dict["is_blocked"] == 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is blocked by administrator. Please contact sports department."
        )
    
    # Generate JWT token
    token_data = {"sub": str(user_dict["id"]), "email": user_dict["email"], "role": user_dict["role"]}
    token = create_access_token(token_data)
    
    user_resp = UserResponse(
        id=user_dict["id"],
        name=user_dict["name"],
        email=user_dict["email"],
        role=user_dict["role"],
        is_blocked=user_dict["is_blocked"],
        created_at=str(user_dict["created_at"])
    )
    
    return TokenResponse(access_token=token, token_type="bearer", user=user_resp)

def list_all_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, role, is_blocked, created_at FROM users ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [UserResponse(**dict(row)) for row in rows]

def block_user_by_id(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, name, email, role, is_blocked FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User with ID {user_id} not found.")
    
    user = dict(row)
    if user["role"] == "admin":
        conn.close()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot block an administrator account.")
    
    cursor.execute("UPDATE users SET is_blocked = 1 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return {"message": f"User ID {user_id} ({user['name']}) has been successfully blocked.", "user_id": user_id, "is_blocked": 1}

def unblock_user_by_id(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, name, email, role, is_blocked FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User with ID {user_id} not found.")
    
    user = dict(row)
    cursor.execute("UPDATE users SET is_blocked = 0 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return {"message": f"User ID {user_id} ({user['name']}) has been successfully unblocked.", "user_id": user_id, "is_blocked": 0}
