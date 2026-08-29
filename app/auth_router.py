from fastapi import APIRouter, Depends
from typing import List
from app.models import UserRegister, UserLogin, UserResponse, TokenResponse
from app.auth import get_current_user, require_admin
import app.auth_service as auth_service

router = APIRouter(prefix="/auth", tags=["Authentication & Users"])

@router.post("/register", response_model=UserResponse)
def register(data: UserRegister):
    return auth_service.register_user(data)

@router.post("/login", response_model=TokenResponse)
def login(data: UserLogin):
    return auth_service.authenticate_user(data)

@router.get("/me", response_model=UserResponse)
def get_me(current_user: dict = Depends(get_current_user)):
    return UserResponse(**current_user)

@router.get("/users", response_model=List[UserResponse])
def get_users(admin: dict = Depends(require_admin)):
    return auth_service.list_all_users()

@router.post("/users/{user_id}/block")
@router.patch("/users/{user_id}/block")
def block_user(user_id: int, admin: dict = Depends(require_admin)):
    return auth_service.block_user_by_id(user_id)

@router.post("/users/{user_id}/unblock")
@router.patch("/users/{user_id}/unblock")
def unblock_user(user_id: int, admin: dict = Depends(require_admin)):
    return auth_service.unblock_user_by_id(user_id)
