from fastapi import APIRouter, Depends, UploadFile, File, Form
from typing import Optional, List, Dict, Any
from app.models import QueryRequest, QueryResponse
from app.auth import get_current_user
import app.query_agent as query_agent
from app.voice_service import voice_service
from app.tournament_solver import TournamentRequest, solve_tournament_schedule, TournamentSolverResult
from app.demand_forecaster import forecaster

router = APIRouter(prefix="/agent", tags=["AI Assistant Agent"])

@router.post("/query", response_model=QueryResponse)
def ask_agent(data: QueryRequest, current_user: dict = Depends(get_current_user)):
    session_id = data.session_id or "default_session"
    return query_agent.process_query(data.query, current_user, session_id=session_id)

@router.post("/voice-query")
async def voice_query_endpoint(
    file: UploadFile = File(...),
    session_id: str = Form("voice_session"),
    current_user: dict = Depends(get_current_user)
):
    audio_bytes = await file.read()
    return voice_service.process_voice_query(
        audio_bytes=audio_bytes,
        user_id=current_user.get("id", 1),
        session_id=session_id,
        user_role=current_user.get("role", "student")
    )

@router.post("/tournament/schedule", response_model=TournamentSolverResult)
def schedule_tournament_endpoint(req: TournamentRequest, current_user: dict = Depends(get_current_user)):
    return solve_tournament_schedule(req)

@router.get("/demand/forecast")
def get_demand_forecast(sport_name: str, booking_date: str, time_slot: str, current_user: dict = Depends(get_current_user)):
    return forecaster.predict_congestion(sport_name, booking_date, time_slot)
