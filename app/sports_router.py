from fastapi import APIRouter, Depends, Query
from typing import List, Optional
from app.models import (
    SportCreate, SportResponse,
    FacilityCreate, FacilityResponse,
    BookingCreate, BookingResponse,
    AttendanceCreate, AttendanceResponse,
    DashboardStats
)
from app.auth import get_current_user, require_admin
import app.sports_service as sports_service

router = APIRouter(tags=["Sports, Facilities, Bookings & Attendance"])

# --- Sports ---
@router.get("/sports", response_model=List[SportResponse])
def get_sports():
    return sports_service.list_sports()

@router.post("/sports", response_model=SportResponse)
def add_sport(data: SportCreate, admin: dict = Depends(require_admin)):
    return sports_service.create_sport(data)

@router.delete("/sports/{sport_id}")
def remove_sport(sport_id: int, admin: dict = Depends(require_admin)):
    return sports_service.delete_sport(sport_id)

# --- Facilities ---
@router.get("/facilities", response_model=List[FacilityResponse])
def get_facilities():
    return sports_service.list_facilities()

@router.post("/facilities", response_model=FacilityResponse)
def add_facility(data: FacilityCreate, admin: dict = Depends(require_admin)):
    return sports_service.create_facility(data)

@router.patch("/facilities/{facility_id}/toggle")
def toggle_facility(facility_id: int, admin: dict = Depends(require_admin)):
    return sports_service.toggle_facility_status(facility_id)

# --- Bookings ---
@router.get("/bookings", response_model=List[BookingResponse])
def get_bookings(
    all_users: bool = Query(False),
    current_user: dict = Depends(get_current_user)
):
    if all_users and current_user["role"] == "admin":
        return sports_service.list_all_bookings()
    return sports_service.list_user_bookings(current_user["id"])

@router.post("/bookings", response_model=BookingResponse)
def make_booking(data: BookingCreate, current_user: dict = Depends(get_current_user)):
    return sports_service.create_booking(current_user["id"], data)

@router.delete("/bookings/{booking_id}")
def cancel_booking_endpoint(booking_id: int, current_user: dict = Depends(get_current_user)):
    is_admin = (current_user["role"] == "admin")
    return sports_service.cancel_booking(booking_id, current_user["id"], is_admin=is_admin)

# --- Attendance ---
@router.get("/attendance", response_model=List[AttendanceResponse])
def get_attendance(admin: dict = Depends(require_admin)):
    return sports_service.list_attendance()

@router.get("/attendance/my", response_model=List[AttendanceResponse])
def get_my_attendance(current_user: dict = Depends(get_current_user)):
    return sports_service.list_user_attendance(current_user["id"])

@router.post("/attendance", response_model=AttendanceResponse)
def record_attendance(data: AttendanceCreate, current_user: dict = Depends(get_current_user)):
    return sports_service.mark_attendance(data, marked_by=current_user["id"])

# --- Dashboard ---
@router.get("/dashboard/overview", response_model=DashboardStats)
def get_dashboard(current_user: dict = Depends(get_current_user)):
    return sports_service.get_dashboard_overview()
