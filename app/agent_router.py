from fastapi import APIRouter, Depends
from app.models import QueryRequest, QueryResponse
from app.auth import get_current_user
import app.query_agent as query_agent

router = APIRouter(prefix="/agent", tags=["AI Assistant Agent"])

@router.post("/query", response_model=QueryResponse)
def ask_agent(data: QueryRequest, current_user: dict = Depends(get_current_user)):
    session_id = data.session_id or "default_session"
    return query_agent.process_query(data.query, current_user, session_id=session_id)
