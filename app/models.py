from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict

# --- User & Auth Models ---
class UserRegister(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., min_length=3, max_length=120)
    password: str = Field(..., min_length=4)
    role: str = Field("student", pattern="^(student|admin)$")

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    is_blocked: int
    created_at: Optional[str] = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

# --- Sports Models ---
class SportCreate(BaseModel):
    name: str
    category: str
    description: Optional[str] = ""
    min_players: int = 1
    max_players: int = 22

class SportResponse(BaseModel):
    id: int
    name: str
    category: str
    description: Optional[str] = None
    min_players: int
    max_players: int
    created_at: Optional[str] = None

# --- Facilities Models ---
class FacilityCreate(BaseModel):
    name: str
    sport_id: int
    location: str
    capacity: int = 10
    is_available: int = 1

class FacilityResponse(BaseModel):
    id: int
    name: str
    sport_id: int
    sport_name: Optional[str] = None
    location: str
    capacity: int
    is_available: int
    created_at: Optional[str] = None

# --- Bookings Models ---
class BookingCreate(BaseModel):
    facility_id: int
    sport_id: int
    booking_date: str # YYYY-MM-DD
    time_slot: str    # e.g., '06:00 - 07:00'
    notes: Optional[str] = ""

class BookingResponse(BaseModel):
    id: int
    user_id: int
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    facility_id: int
    facility_name: Optional[str] = None
    sport_id: int
    sport_name: Optional[str] = None
    booking_date: str
    time_slot: str
    status: str
    notes: Optional[str] = None
    created_at: Optional[str] = None

# --- Attendance Models ---
class AttendanceCreate(BaseModel):
    booking_id: int
    user_id: int
    status: str = "present" # present, absent, late

class AttendanceResponse(BaseModel):
    id: int
    booking_id: int
    user_id: int
    user_name: Optional[str] = None
    check_in_time: Optional[str] = None
    status: str
    marked_by: Optional[int] = None
    marked_by_name: Optional[str] = None
    booking_date: Optional[str] = None
    time_slot: Optional[str] = None
    facility_name: Optional[str] = None
    sport_name: Optional[str] = None

# --- Dashboard Models ---
class DashboardStats(BaseModel):
    total_users: int
    active_students: int
    total_sports: int
    total_facilities: int
    total_bookings: int
    today_bookings: int
    attendance_rate: float
    recent_bookings: List[Dict[str, Any]]

# --- AI Assistant Query Models ---
class QueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = "default_session"

class QueryResponse(BaseModel):
    intent: str
    message: str
    success: bool = True
    action_taken: Optional[str] = None
    data: Optional[Any] = None
    pending_confirmation: bool = False
    suggested_slots: Optional[List[str]] = None
