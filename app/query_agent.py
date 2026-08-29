import re
import json
import logging
import requests
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, List, Tuple
from app.config import GEMINI_API_KEY
from app.models import QueryResponse
import app.agent_tools as tools
import app.sports_service as sports_service
from app.constraint_engine import validate_booking_request, validate_cancellation_request
from app.agents.orchestrator import SportsOrchestrator

logger = logging.getLogger("sports_erp.query_agent")
logger.setLevel(logging.INFO)

# Global multi-agent orchestrator instance
orchestrator = SportsOrchestrator()

# Session memory store: session_key -> { "history": [...], "pending_action": {...}, "last_entities": {...} }
SESSION_STORE: Dict[str, Dict[str, Any]] = {}

def get_or_create_session(session_id: str, user_id: int) -> Dict[str, Any]:
    key = f"{user_id}_{session_id}"
    if key not in SESSION_STORE:
        SESSION_STORE[key] = {
            "history": [],
            "pending_action": None,
            "last_entities": {
                "sport": None,
                "date": None,
                "time_slot": None,
                "available_slots": []
            }
        }
    return SESSION_STORE[key]

# --- NATURAL LANGUAGE ENTITY EXTRACTORS ---

SPORTS_SYNONYMS = {
    "badminton": "Badminton",
    "shuttle": "Badminton",
    "baddy": "Badminton",
    "cricket": "Cricket",
    "football": "Football",
    "soccer": "Football",
    "turf": "Football",
    "basketball": "Basketball",
    "hoops": "Basketball",
    "swimming": "Swimming",
    "swim": "Swimming",
    "pool": "Swimming",
    "table tennis": "Table Tennis",
    "tt": "Table Tennis",
    "ping pong": "Table Tennis",
    "pingpong": "Table Tennis",
    "tennis": "Tennis",
    "lawn tennis": "Tennis",
    "volleyball": "Volleyball",
    "squash": "Squash"
}

def extract_sport(text: str, fallback_sport: Optional[str] = None) -> Optional[str]:
    low = text.lower()
    for syn, canonical in SPORTS_SYNONYMS.items():
        if re.search(rf"\b{re.escape(syn)}\b", low):
            return canonical
    return fallback_sport

def extract_date_explicit(text: str) -> Optional[str]:
    low = text.lower()
    today = date.today()
    if re.search(r"\b(?:aaj|today|tonight)\b", low):
        return today.isoformat()
    if re.search(r"\b(?:kal|tomorrow)\b", low):
        return (today + timedelta(days=1)).isoformat()
    if re.search(r"\b(?:parso|day after tomorrow)\b", low):
        return (today + timedelta(days=2)).isoformat()
    
    match_iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if match_iso:
        return match_iso.group(1)
    
    return None

def extract_date(text: str, fallback_date: Optional[str] = None) -> str:
    explicit = extract_date_explicit(text)
    if explicit:
        return explicit
    return fallback_date or (date.today() + timedelta(days=1)).isoformat()

def extract_time_slot(text: str, fallback_slot: Optional[str] = None) -> Optional[str]:
    """
    Robust natural-language time slot extractor supporting standard slot formats,
    12-hour AM/PM times, 24-hour times, time ranges, and Hinglish expressions.
    """
    # Strip ISO and slash dates first so hyphens in dates (like 2026-11-20) are not confused with time ranges
    low = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " ", text.lower())
    low = re.sub(r"\b\d{1,2}/\d{1,2}/\d{4}\b", " ", low).strip()
    
    # 1. Direct match for standard range (e.g. "06:00 - 07:00", "09:00 - 10:00", "17:00 to 18:00")
    m_range = re.search(r"\b(0?\d|1\d|2[0-3]):00\s*(?:-|to)\s*(0?\d|1\d|2[0-3]):00\b", low)
    if m_range:
        h1 = int(m_range.group(1))
        h2 = int(m_range.group(2))
        return f"{h1:02d}:00 - {h2:02d}:00"

    # 2. Number to number with AM/PM/subah/shaam (e.g. "8 to 9 am", "8-9 am", "5 to 6 pm", "5-6", "8 to 9")
    m_range_num = re.search(r"\b(0?\d|1\d|2[0-3])\s*(?:-|to)\s*(0?\d|1\d|2[0-3])\s*(am|pm|subah|shaam|evening|night)?\b", low)
    if m_range_num:
        h1 = int(m_range_num.group(1))
        h2 = int(m_range_num.group(2))
        meridiem = m_range_num.group(3)
        if meridiem in ["pm", "shaam", "evening", "night"] and h1 < 12:
            h1 += 12
            h2 += 12
        elif (meridiem in ["am", "subah"] or not meridiem) and h1 == 12:
            h1 = 0
            h2 = 1
        elif not meridiem and h1 in [4, 5, 6, 7, 8] and "shaam" in low:
            h1 += 12
            h2 += 12
        return f"{h1:02d}:00 - {h2:02d}:00"

    # 3. Explicit AM / PM times (e.g. "9 am", "9am", "9:00 am", "5 pm", "5pm", "12 pm", "12 am", "7 am")
    m_ampm = re.search(r"\b(0?\d|1\d|2[0-3])(?::([0-5]\d))?\s*(am|pm)\b", low)
    if m_ampm:
        h = int(m_ampm.group(1))
        merid = m_ampm.group(3)
        if merid == "pm" and h != 12:
            h += 12
        elif merid == "am" and h == 12:
            h = 0
        return f"{h:02d}:00 - {(h + 1) % 24:02d}:00"

    # 4. Hinglish expressions (e.g. "subah 9 baje", "9 baje subah", "shaam 5 baje", "5 baje shaam", "5 baje", "9 baje")
    m_hi_pre = re.search(r"\b(subah|shaam|dopahar|raat)\s*(?:ke\s*)?(0?\d|1\d|2[0-3])\s*(?:baje)?\b", low)
    if m_hi_pre:
        period = m_hi_pre.group(1)
        h = int(m_hi_pre.group(2))
        if period in ["shaam", "raat"] and h < 12:
            h += 12
        elif period == "dopahar" and h < 12 and h != 12:
            h += 12
        elif period == "subah" and h == 12:
            h = 0
        return f"{h:02d}:00 - {(h + 1) % 24:02d}:00"

    m_hi_post = re.search(r"\b(0?\d|1\d|2[0-3])\s*baje\s*(subah|shaam|dopahar|raat|pm|am)?\b", low)
    if m_hi_post:
        h = int(m_hi_post.group(1))
        period = m_hi_post.group(2)
        if period in ["shaam", "raat", "pm"] and h < 12:
            h += 12
        elif period in ["dopahar"] and h < 12 and h != 12:
            h += 12
        elif period in ["subah", "am"] and h == 12:
            h = 0
        elif not period and h in [4, 5, 6, 7]:
            h += 12
        return f"{h:02d}:00 - {(h + 1) % 24:02d}:00"

    # 5. Standalone 24-hour format (e.g. "06:00", "07:00", "08:00", "09:00", "16:00", "17:00", "18:00", "19:00")
    m_24h = re.search(r"\b(0[0-9]|1[0-9]|2[0-3]):00\b", low)
    if m_24h:
        h = int(m_24h.group(1))
        return f"{h:02d}:00 - {(h + 1) % 24:02d}:00"

    # 6. Special keywords
    if "noon" in low or "midday" in low:
        return "12:00 - 13:00"
    if "midnight" in low:
        return "00:00 - 01:00"

    return fallback_slot

def extract_ordinal_slot(text: str, available_slots: List[str]) -> Optional[str]:
    if not available_slots:
        return None
    low = text.lower()
    if re.search(r"\b(?:first|1st)\b", low) and len(available_slots) >= 1:
        return available_slots[0]
    if re.search(r"\b(?:second|2nd)\b", low) and len(available_slots) >= 2:
        return available_slots[1]
    if re.search(r"\b(?:third|3rd)\b", low) and len(available_slots) >= 3:
        return available_slots[2]
    if re.search(r"\b(?:fourth|4th)\b", low) and len(available_slots) >= 4:
        return available_slots[3]
    if re.search(r"\b(?:that\s+slot|this\s+slot|the\s+slot|it)\b", low) and len(available_slots) >= 1:
        return available_slots[0]
    return None

def is_affirmation(text: str) -> bool:
    low = text.lower().strip()
    affirmative = [
        "yes", "haan", "ha", "haa", "kar do", "kardo", "confirm", "ok", "sure",
        "yup", "yeah", "book it", "block it", "proceed", "done", "theek hai", "chalega", "yes please", "please do"
    ]
    if low in ["y", "yes", "haan", "ha", "haa", "yes.", "haanji", "han", "ok", "confirm", "sure", "book it", "proceed", "yes please", "please do"]:
        return True
    return any(re.search(rf"^(?:{re.escape(w)})$", low) for w in affirmative) or any(re.search(rf"\b{re.escape(w)}\b", low) for w in ["kar do", "kardo", "book it", "confirm it", "proceed"])

def is_negation(text: str) -> bool:
    low = text.lower().strip()
    negative = ["no", "nahi", "nahin", "mat karo", "cancel", "nope", "nevermind", "dont", "don't", "cancel action", "stop"]
    if low in ["n", "no", "nahi", "nahin", "no.", "nope", "cancel", "mat karo", "stop"]:
        return True
    return any(re.search(rf"\b{re.escape(w)}\b", low) for w in negative)

# --- MAIN ORCHESTRATOR ---

def process_query(query: str, current_user: Dict[str, Any], session_id: str = "default_session") -> QueryResponse:
    user_id = current_user.get("id", 0)
    user_role = current_user.get("role", "student")
    user_name = current_user.get("name", "User")
    user_email = current_user.get("email", "")
    
    session = get_or_create_session(session_id, user_id)
    raw_query = query.strip()
    q = raw_query.lower()

    # --- 1. CHECK PENDING CONFIRMATION ACTION ---
    pending = session.get("pending_action")
    if pending:
        pa_time = pending.get("timestamp")
        is_expired = False
        if pa_time and (datetime.now() - pa_time) > timedelta(minutes=10):
            is_expired = True
            session["pending_action"] = None
        
        if is_expired:
            if is_affirmation(q) or is_negation(q):
                return QueryResponse(
                    intent="pending_action_expired",
                    message="Your previous pending confirmation has expired due to inactivity. Please make a new booking or action request.",
                    success=False
                )
        elif is_affirmation(q):
            action_type = pending.get("type")
            session["pending_action"] = None # Clear pending state

            if action_type == "availability_followup":
                # User affirmed interest in booking following an availability check.
                # Validate constraints deterministically (TRACE-CS)
                c_val = validate_booking_request(
                    user_id=user_id,
                    sport_name=pending["sport_name"],
                    booking_date=pending["booking_date"],
                    time_slot=pending["time_slot"],
                    facility_id=pending.get("facility_id"),
                    user_role=user_role
                )
                if not c_val.is_valid:
                    return QueryResponse(
                        intent="booking_failed",
                        message=f"❌ {c_val.explanation}",
                        success=False,
                        suggested_slots=c_val.suggested_alternatives
                    )
                
                # Arm for final booking confirmation (Do NOT commit to database yet)
                fac_name = c_val.details.get("facility_name", pending.get("facility_name", "Court"))
                session["pending_action"] = {
                    "type": "book_slot",
                    "sport_name": pending["sport_name"],
                    "facility_id": c_val.details.get("facility_id", pending.get("facility_id")),
                    "facility_name": fac_name,
                    "booking_date": pending["booking_date"],
                    "time_slot": pending["time_slot"],
                    "timestamp": datetime.now()
                }
                return QueryResponse(
                    intent="confirm_booking_request",
                    message=f"Please confirm: Would you like to book {fac_name} ({pending['sport_name']}) on {pending['booking_date']} from {pending['time_slot']}?",
                    success=True,
                    pending_confirmation=True,
                    data=c_val.details
                )

            elif action_type == "book_slot":
                # Deterministic constraint validation (TRACE-CS)
                c_val = validate_booking_request(
                    user_id=user_id,
                    sport_name=pending["sport_name"],
                    booking_date=pending["booking_date"],
                    time_slot=pending["time_slot"],
                    facility_id=pending.get("facility_id"),
                    user_role=user_role
                )
                if not c_val.is_valid:
                    return QueryResponse(
                        intent="booking_failed",
                        message=f"❌ {c_val.explanation}",
                        success=False,
                        suggested_slots=c_val.suggested_alternatives
                    )

                res = tools.create_booking_tool(
                    user_id=user_id,
                    sport_name=pending["sport_name"],
                    booking_date=pending["booking_date"],
                    time_slot=pending["time_slot"],
                    notes="Booked via AI Assistant"
                )
                return QueryResponse(
                    intent="booking_confirmed",
                    message=f"✅ {res['message']}",
                    success=res["success"],
                    action_taken="create_booking",
                    data=res.get("data")
                )
            
            elif action_type == "block_user":
                if user_role != "admin":
                    return QueryResponse(
                        intent="admin_command_denied",
                        message="Permission Denied: You don't have permission to perform this action. Only administrators can block users.",
                        success=False
                    )
                res = tools.block_user_tool(role=user_role, user_identifier=str(pending["target_id"]))
                return QueryResponse(
                    intent="user_blocked",
                    message=f"✅ {res['message']}",
                    success=res["success"],
                    action_taken="block_user",
                    data=res.get("data")
                )

            elif action_type == "unblock_user":
                if user_role != "admin":
                    return QueryResponse(
                        intent="admin_command_denied",
                        message="Permission Denied: You don't have permission to perform this action. Only administrators can unblock users.",
                        success=False
                    )
                res = tools.unblock_user_tool(role=user_role, user_identifier=str(pending["target_id"]))
                return QueryResponse(
                    intent="user_unblocked",
                    message=f"✅ {res['message']}",
                    success=res["success"],
                    action_taken="unblock_user",
                    data=res.get("data")
                )

        elif is_negation(q):
            session["pending_action"] = None
            return QueryResponse(
                intent="action_cancelled",
                message="Understood. The action has been cancelled.",
                success=True
            )
        else:
            # Unrelated question arrived while confirmation was pending.
            # Safely disarm the pending action so subsequent turns do not accidentally trigger it.
            session["pending_action"] = None

    # --- 2. USER IDENTITY QUERY ("Who am I?", "What is my email?") ---
    identity_patterns = [
        r"\bwho\s+am\s+i\b",
        r"\bwho\s+am\s+i\s+logged\s+in\s+as\b",
        r"\bwhoami\b",
        r"\bcurrent\s+user\b",
        r"\bmera\s+naam\b",
        r"\blogged\s+in\s+as\b",
        r"\bmera\s+account\b",
        r"\bmy\s+profile\b",
        r"\bmy\s+account\b",
        r"\buser\s+details\b",
        r"\bwho\s+is\s+logged\s+in\b",
        r"\bwhat\s+(?:is\s+)?my\s+email\b",
        r"\bwhom\s+am\s+i\b"
    ]
    if any(re.search(pat, q) for pat in identity_patterns):
        return QueryResponse(
            intent="who_am_i",
            message=f"You are currently logged in as **{user_name}**, {user_role.title()} ({user_email}).",
            success=True,
            data={"name": user_name, "role": user_role, "email": user_email, "id": user_id}
        )

    # --- 3. USER ROLE QUERY ("Am I a student or admin?", "What is my role?") ---
    role_patterns = [
        r"\bmera\s+role\b",
        r"\bwhat\s+(?:is\s+)?my\s+role\b",
        r"\bmy\s+role\b",
        r"\brole\s+kya\s+hai\b",
        r"\buser\s+role\b",
        r"\bwhich\s+role\b",
        r"\bwhat\s+type\s+of\s+user\b",
        r"\bam\s+i\s+(?:a\s+|an\s+)?(?:student|admin)(?:\s+or\s+(?:a\s+|an\s+)?(?:student|admin))?\b",
        r"\bkya\s+main\s+(?:admin|student)\s+hoon\b",
        r"\bwho\s+role\b"
    ]
    if any(re.search(pat, q) for pat in role_patterns):
        return QueryResponse(
            intent="user_role_info",
            message=f"Your current system role is **{user_role.title()}**.",
            success=True,
            data={"role": user_role}
        )

    # --- 4. CATALOG & FACILITIES INFO QUERY ---
    if any(re.search(rf"\b{re.escape(k)}\b", q) for k in [
        "catalog", "show catalog", "show my catalog", "sports catalog", "facilities catalog",
        "view catalog", "list catalog", "all catalog", "sports and facilities"
    ]):
        sports_res = tools.list_sports_tool()
        fac_res = tools.list_facilities_tool()
        sports_list = sports_res.get("data", [])
        fac_list = fac_res.get("data", [])
        
        sport_names = ", ".join([s["name"] for s in sports_list])
        msg = (
            f"🏅 **Campus Sports Catalog**:\n"
            f"• **Available Sports ({len(sports_list)}):** {sport_names}\n"
            f"• **Active Facilities ({len(fac_list)}):** {len(fac_list)} courts, fields & pools available on campus.\n"
            f"You can explore full details in the Sports & Facilities tabs, or ask me *'Is Badminton available tomorrow at 5 PM?'* to check slots!"
        )
        return QueryResponse(
            intent="show_catalog",
            message=msg,
            success=True,
            data={"sports": sports_list, "facilities": fac_list}
        )

    # --- 5. ADMIN ACTIONS: BLOCK / UNBLOCK ---
    target_block = None
    if "unblock" not in q and "block" in q:
        m_hi = re.search(r"\b(?:user\s+)?(?:id\s+)?#?([a-zA-Z0-9_@.]+)\s+ko\s+block\b", q)
        m_en = re.search(r"\bblock\s+(?:user\s+)?(?:id\s+)?#?([a-zA-Z0-9_@.]+)", q)
        if m_hi:
            target_block = m_hi.group(1).strip()
        elif m_en:
            target_block = m_en.group(1).strip()

    if target_block:
        target = target_block
        if user_role != "admin":
            return QueryResponse(
                intent="admin_command_denied",
                message="You don't have permission to perform this action. Only administrators can block users.",
                success=False
            )
        
        user_info = None
        users = tools.list_all_users_tool("admin").get("data", [])
        for u in users:
            if target.isdigit() and u["id"] == int(target):
                user_info = u
                break
            elif target.lower() in u["name"].lower() or target.lower() in u["email"].lower():
                user_info = u
                break

        if not user_info:
            return QueryResponse(
                intent="block_user_failed",
                message=f"User '{target}' was not found in the campus user directory.",
                success=False
            )

        if user_info["role"] == "admin":
            return QueryResponse(
                intent="block_user_failed",
                message=f"Cannot block '{user_info['name']}' because they are an administrator.",
                success=False
            )

        session["pending_action"] = {
            "type": "block_user",
            "target_id": user_info["id"],
            "target_name": user_info["name"],
            "timestamp": datetime.now()
        }
        return QueryResponse(
            intent="confirm_block_user",
            message=f"{user_info['name']} (ID #{user_info['id']}) is currently active. Are you sure you want to block this user?",
            pending_confirmation=True,
            data=user_info
        )

    target_unblock = None
    if "unblock" in q:
        m_un_hi = re.search(r"\b(?:user\s+)?(?:id\s+)?#?([a-zA-Z0-9_@.]+)\s+ko\s+unblock\b", q)
        m_un_en = re.search(r"\bunblock\s+(?:user\s+)?(?:id\s+)?#?([a-zA-Z0-9_@.]+)", q)
        if m_un_hi:
            target_unblock = m_un_hi.group(1).strip()
        elif m_un_en:
            target_unblock = m_un_en.group(1).strip()

    if target_unblock:
        target = target_unblock
        if user_role != "admin":
            return QueryResponse(
                intent="admin_command_denied",
                message="You don't have permission to perform this action. Only administrators can unblock users.",
                success=False
            )
        
        user_info = None
        users = tools.list_all_users_tool("admin").get("data", [])
        for u in users:
            if target.isdigit() and u["id"] == int(target):
                user_info = u
                break
            elif target.lower() in u["name"].lower() or target.lower() in u["email"].lower():
                user_info = u
                break

        if not user_info:
            return QueryResponse(
                intent="unblock_user_failed",
                message=f"User '{target}' was not found in the database.",
                success=False
            )

        res = tools.unblock_user_tool("admin", str(user_info["id"]))
        return QueryResponse(
            intent="user_unblocked",
            message=f"✅ {res['message']}",
            success=res["success"],
            data=res.get("data")
        )

    # --- 6. CHECK FOR THIRD-PARTY BOOKING RESTRICTION ---
    is_third_party_book = re.search(r"\bfor\s+(?:user\s+)?([a-zA-Z0-9_@.]+)\b", q)
    non_user_entities = list(SPORTS_SYNONYMS.keys()) + [
        "me", "myself", "my", "self", "own", "us", "student", "students", "admin",
        "playing", "practice", "game", "match", "court", "courts", "facility", "facilities",
        "today", "tomorrow", "kal", "aaj", "parso", "tonight", "hours", "hour", "slot", "slots",
        user_name.lower()
    ]
    if is_third_party_book and any(k in q for k in ["book", "reserve", "slot"]):
        target_name_entity = is_third_party_book.group(1).strip().lower()
        if target_name_entity not in non_user_entities and not target_name_entity.isdigit():
            if user_role != "admin":
                return QueryResponse(
                    intent="booking_on_behalf_denied",
                    message="You can only create bookings for your own account. Students cannot book on behalf of other users.",
                    success=False
                )

    # --- 7. ADMIN CAMPUS-WIDE BOOKINGS & ATTENDANCE OVERVIEW ---
    admin_bookings_patterns = [
        r"\b(?:show\s+|list\s+|view\s+)?(?:today'?s|todays|today|aaj\s+ki)\s+bookings?\b",
        r"\b(?:show\s+|list\s+|view\s+)?all\s+(?:campus\s+)?bookings?\b",
        r"\b(?:all\s+|campus\s+)bookings?\b",
        r"\bfacility\s+bookings?\b",
        r"\bshow\s+attendance\s+overview\b"
    ]
    if user_role == "admin" and any(re.search(pat, q) for pat in admin_bookings_patterns):
        if "attendance" in q:
            res = tools.get_dashboard_stats_tool()
            return QueryResponse(
                intent="get_dashboard_stats",
                message=f"Campus Attendance Overview: Overall check-in attendance rate is {res.get('data', {}).get('attendance_rate', 0.0)}%.",
                success=True,
                data=res.get("data")
            )
        filter_d = date.today().isoformat() if any(k in q for k in ["today", "todays", "today's", "aaj"]) else None
        res = tools.get_all_bookings_tool("admin", filter_date=filter_d)
        return QueryResponse(
            intent="get_all_bookings",
            message=res["message"],
            success=True,
            data=res["data"]
        )

    # --- 8. ACTION: CANCEL BOOKING ---
    is_cancel_action = (
        any(re.search(pat, q) for pat in [
            r"\bcancel\s+(?:my\s+|the\s+)?(?:latest\s+|next\s+|upcoming\s+|past\s+)?(?:booking|reservation|slot)\b",
            r"\bcancel\s+(?:the\s+)?latest\s+one\b",
            r"\bcancel\s+(?:booking\s+)?(?:id\s+)?#?\d+\b",
            r"\bcancel\s+[a-zA-Z]+\s+booking\b",
            r"\bbooking\s+cancel\b",
            r"\bradd\s+kar\b",
            r"\bhata\s+do\b"
        ]) and not any(k in q for k in ["show", "list", "view", "dikhao", "batao", "history", "status"])
    )

    if is_cancel_action:
        b_id = 0
        m = re.search(r"\b(?:id|booking|#)\s*#?(\d+)\b", raw_query.lower())
        if m:
            b_id = int(m.group(1))
        
        sport = extract_sport(raw_query, None)
        target_t = "next" if ("next" in q or "upcoming" in q) else "latest"
        b_date = extract_date_explicit(raw_query) or ""
        b_slot = extract_time_slot(raw_query) or ""
        
        res = tools.cancel_booking_tool(
            user_id=user_id,
            role=user_role,
            sport_name=sport or "",
            booking_id=b_id,
            booking_date=b_date,
            time_slot=b_slot,
            target_type=target_t
        )
        return QueryResponse(
            intent="cancel_booking",
            message=f"✅ {res['message']}" if res["success"] else f"⚠️ {res['message']}",
            success=res["success"],
            data=res.get("data")
        )

    # --- 9. QUERY: VIEW BOOKINGS (Read / View bookings) ---
    is_analytics_intent_query = any(k in q for k in [
        "utilization", "peak", "busy hours", "rush hours", "popularity", "popular sport",
        "popular sports", "cancellation statistics", "cancellation rate", "cancellation stats",
        "analytics", "kitni bookings cancel"
    ])

    is_view_bookings_query = (
        not is_analytics_intent_query and (
            any(re.search(pat, q) for pat in [
                r"\b(?:meri|mera|my|all|active|upcoming|past|today's|todays|cancelled)\s+(?:active\s+|upcoming\s+|all\s+|cancelled\s+)?bookings?\b",
                r"\b(?:show|list|view|get|check|display|dikhao|batao)\s+(?:all\s+|my\s+|meri\s+|active\s+|upcoming\s+|cancelled\s+)*bookings?\b",
                r"\bdo\s+i\s+have\s+(?:any\s+)?(?:active\s+|upcoming\s+|past\s+)?bookings?\b",
                r"\bwhat\s+bookings?\s+do\s+i\s+have\b",
                r"\bwhen\s+is\s+my\s+next\s+booking\b",
                r"\bnext\s+booking\b",
                r"\bcheck\s+(?:my\s+)?slots?\b",
                r"\bmera\s+schedule\b",
                r"\bmy\s+schedule\b",
                r"\bbookings?\s+(?:kya\s+hain|kya\s+hai|dikhao|list|status|history)\b"
            ]) or
            (any(k in q for k in ["booking", "bookings"]) and any(k in q for k in ["show", "list", "view", "dikhao", "batao", "status", "history", "active", "upcoming", "my all", "all my", "do i have", "have i", "any"]))
        )
    )

    is_direct_book_word = any(re.search(pat, q) for pat in [
        r"\bbook\b",
        r"\breserve\b",
        r"\bkhelna\s+hai\b"
    ]) and not is_view_bookings_query and not is_cancel_action

    if is_view_bookings_query and not is_cancel_action and not is_direct_book_word and not is_analytics_intent_query:
        filter_type = "all"
        if "today" in q or "aaj" in q:
            filter_type = "today"
        elif "next" in q or "agli" in q:
            filter_type = "next"
        elif "cancelled" in q or "canceled" in q or "cancel" in q:
            filter_type = "cancelled"
        elif "upcoming" in q or "aane wali" in q:
            filter_type = "upcoming"
        elif "active" in q or "confirmed" in q:
            filter_type = "active"

        res = tools.search_my_bookings(user_id, filter_type=filter_type)
        return QueryResponse(
            intent="search_my_bookings",
            message=res["message"],
            success=True,
            data=res["data"]
        )

    # --- 10. QUERY: ATTENDANCE ---
    attendance_patterns = [
        r"\b(?:show\s+|view\s+|get\s+|check\s+|meri\s+)?attendance\b",
        r"\bmeri\s+attendance\b",
        r"\battendance\s+(?:percentage|rate|summary|history|dikhao|batao|kitni\s+hai|kya\s+hai)\b",
        r"\b(?:how\s+many\s+)?sessions?\s+(?:have\s+i\s+)?(?:attended|missed)\b",
        r"\bhow\s+much\s+is\s+my\s+attendance\b",
        r"\bcheck\s*in\s*records?\b",
        r"\battended\b",
        r"\bmissed\s+sessions?\b"
    ]
    if any(re.search(pat, q) for pat in attendance_patterns) or any(k in q for k in ["attendance", "meri attendance"]):
        if user_role == "admin" and ("overview" in q or "all" in q or "system" in q or "campus" in q):
            res = tools.get_dashboard_stats_tool()
            return QueryResponse(
                intent="get_dashboard_stats",
                message=f"Campus Attendance Overview: Overall check-in attendance rate is {res.get('data', {}).get('attendance_rate', 0.0)}%.",
                success=True,
                data=res.get("data")
            )
        sport = extract_sport(raw_query)
        res = tools.get_user_attendance_tool(user_id, sport_name=sport or "")
        return QueryResponse(
            intent="get_user_attendance",
            message=res["message"],
            success=True,
            data=res["data"]
        )

    # --- 11. QUERY: LIST ALL USERS / USER DIRECTORY (Strictly Admin only) ---
    if any(k in q for k in ["show all users", "list all users", "show users", "list users", "all users", "show blocked users", "show student users", "how many users", "total users", "users kitne"]):
        if user_role != "admin":
            return QueryResponse(
                intent="admin_command_denied",
                message="You don't have permission to perform this action.",
                success=False
            )
        
        if "blocked" in q:
            res = tools.list_filtered_users_tool("admin", "blocked")
        elif "student" in q:
            res = tools.list_filtered_users_tool("admin", "student")
        elif "admin" in q:
            res = tools.list_filtered_users_tool("admin", "admin")
        else:
            res = tools.list_filtered_users_tool("admin", "all")
            
        return QueryResponse(
            intent="list_all_users",
            message=res["message"],
            success=True,
            data=res["data"]
        )

    # --- 12. QUERY: LIST SPORTS / LIST FACILITIES ---
    if any(k in q for k in ["list sports", "available sports", "kaun kaun se sports", "what sports", "sports dikhao", "what sports are available", "show available sports", "what sports can i play"]):
        res = tools.list_sports_tool()
        return QueryResponse(
            intent="list_sports",
            message=res["message"],
            success=True,
            data=res["data"]
        )

    if any(k in q for k in ["what facilities are available", "which facilities are available", "facilities", "courts", "grounds", "which courts are available", "kaunse courts", "free courts", "available facilities", "show facilities", "which facility is used"]):
        sport = extract_sport(raw_query)
        res = tools.list_facilities_tool(sport or "")
        return QueryResponse(
            intent="list_facilities",
            message=res["message"],
            success=True,
            data=res["data"]
        )

    # --- 13. DEDICATED ERP ANALYTICS INTENTS ---
    # 13.1 Facility Utilization
    if any(k in q for k in [
        "facility utilization", "court utilization", "utilization analytics", "utilization rate",
        "facilities utilization", "ground utilization", "facilities kitni busy", "court usage",
        "facility usage", "kaun sa court kitna use", "court utilization rate"
    ]):
        res = tools.get_facility_utilization_tool()
        return QueryResponse(
            intent="facility_utilization",
            message=res["message"],
            success=True,
            data=res["data"]
        )

    # 13.2 Peak Booking Hours
    if any(k in q for k in [
        "peak booking hours", "peak hours", "busy hours", "rush hours", "peak time",
        "busiest slot", "kaunsa time sabse busy", "peak slots", "rush time", "busiest time", "busiest hours"
    ]):
        res = tools.get_peak_booking_hours_tool()
        return QueryResponse(
            intent="peak_booking_hours",
            message=res["message"],
            success=True,
            data=res["data"]
        )

    # 13.3 Sport Popularity
    if any(k in q for k in [
        "sport popularity", "popular sports", "most played sport", "most popular sport",
        "top sports", "sabse popular sport", "kaunsa sport sabse zyada", "sports popularity",
        "popularity of sports", "most booked sport"
    ]):
        res = tools.get_sport_popularity_tool()
        return QueryResponse(
            intent="sport_popularity",
            message=res["message"],
            success=True,
            data=res["data"]
        )

    # 13.4 Cancellation Statistics
    if any(k in q for k in [
        "cancellation statistics", "cancellation rate", "cancelled bookings stats",
        "how many bookings are cancelled", "kitni bookings cancel hui", "cancellation metrics",
        "cancellations stats", "booking cancellation rate", "cancellation stats", "cancellation report"
    ]):
        res = tools.get_cancellation_statistics_tool(user_id=user_id, role=user_role)
        return QueryResponse(
            intent="cancellation_statistics",
            message=res["message"],
            success=True,
            data=res["data"]
        )

    # 13.5 Comprehensive Advanced Analytics
    if any(k in q for k in [
        "advanced analytics", "analytics overview", "comprehensive analytics",
        "erp analytics", "show analytics", "view analytics", "analytics"
    ]):
        if user_role == "admin":
            analytics = sports_service.get_advanced_analytics()
            top_sport = analytics.popular_sports[0]["sport_name"] if analytics.popular_sports else "None"
            peak_slot = analytics.peak_hours_distribution[0]["time_slot"] if analytics.peak_hours_distribution else "None"
            msg = (
                f"📊 **Advanced Sports ERP Analytics**:\n"
                f"• **Total Bookings:** {analytics.total_bookings} ({analytics.active_confirmed_bookings} active, {analytics.cancelled_bookings} cancelled, {analytics.cancellation_rate}% cancellation rate)\n"
                f"• **Facility Utilization Rate:** {analytics.facility_utilization_rate}%\n"
                f"• **Most Popular Sport:** {top_sport}\n"
                f"• **Peak Booking Interval:** {peak_slot}\n"
                f"• **Attendance Present Rate:** {analytics.attendance_present_rate}%"
            )
            return QueryResponse(
                intent="advanced_analytics",
                message=msg,
                success=True,
                data=analytics.model_dump()
            )
        else:
            att = tools.get_user_attendance_tool(user_id)
            book = tools.search_my_bookings(user_id)
            return QueryResponse(
                intent="student_analytics",
                message=f"Your Personal Sports Analytics: {book['active_count']} active bookings, {att['count']} total sessions attended with a {att['attendance_rate']}% attendance rate.",
                success=True,
                data={"bookings": book, "attendance": att}
            )

    # 13.6 General Dashboard Stats / Overview
    if any(k in q for k in ["overview", "dashboard", "summary", "stats", "statistics", "report", "sports erp overview"]):
        res = tools.get_dashboard_stats_tool()
        return QueryResponse(
            intent="get_dashboard_stats",
            message=res["message"],
            success=True,
            data=res["data"]
        )

    # --- 14. ACTION: BOOKING & AVAILABILITY FLOW ---
    is_explicit_book_action = (
        any(re.search(pat, q) for pat in [
            r"\bbook\b",
            r"\breserve\b",
            r"\bkhelna\s+hai\b",
            r"\bslot\s+chahiye\b",
            r"\bslot\s+book\b",
            r"\bbook\s+(?:a\s+)?court\b",
            r"\bfind\s+(?:an\s+)?available\s+slot\s+and\s+book\b"
        ]) and not is_view_bookings_query and not is_cancel_action
    )
    
    is_avail_query = any(re.search(pat, q) for pat in [
        r"\bavailable\b",
        r"\bfree\b",
        r"\bkhali\b",
        r"\bslots?\s+batao\b",
        r"\bcheck\s+availability\b",
        r"\bwhich\s+slots?\b",
        r"\bavailable\s+hai\b",
        r"\bfree\s+hai\b",
        r"\bkhali\s+hai\b",
        r"\bslot\s+available\b",
        r"\bkoi\s+available\s+slot\b",
        r"\bavailable\s+slots?\b",
        r"\bis\s+[a-zA-Z0-9_]+\s+available\b"
    ])
    
    sport_in_query = extract_sport(raw_query, None)
    slot_in_query = extract_time_slot(raw_query, None)
    ordinal_slot = extract_ordinal_slot(raw_query, session["last_entities"].get("available_slots", []))
    resolved_slot_in_q = slot_in_query or ordinal_slot
    date_in_query = extract_date_explicit(raw_query)

    should_run_booking_or_avail = (
        is_explicit_book_action or
        is_avail_query or
        (sport_in_query and resolved_slot_in_q) or
        (resolved_slot_in_q and session["last_entities"].get("sport")) or
        (is_explicit_book_action and session["last_entities"].get("sport"))
    )

    if should_run_booking_or_avail:
        detected_sport = sport_in_query or session["last_entities"].get("sport")
        detected_date = date_in_query or session["last_entities"].get("date") or (date.today() + timedelta(days=1)).isoformat()
        
        if resolved_slot_in_q:
            detected_slot = resolved_slot_in_q
        elif is_explicit_book_action and not (sport_in_query or date_in_query):
            detected_slot = session["last_entities"].get("time_slot")
        elif not is_explicit_book_action and not is_avail_query:
            detected_slot = session["last_entities"].get("time_slot")
        else:
            detected_slot = None

        if not detected_sport:
            return QueryResponse(
                intent="missing_sport",
                message="Which sport would you like to check or book? (e.g. Badminton, Cricket, Football, Basketball, Swimming, Table Tennis)",
                success=True
            )
        
        session["last_entities"]["sport"] = detected_sport
        session["last_entities"]["date"] = detected_date
        session["last_entities"]["time_slot"] = detected_slot

        # Case A: Slot is not specified -> list all available slots from real SQLite DB
        if not detected_slot:
            alt = tools.find_alternative_slots(detected_sport, detected_date)
            slots = alt.get("available_slots", [])
            session["last_entities"]["available_slots"] = slots
            slot_str = ", ".join(slots) if slots else "No slots open"
            
            if is_explicit_book_action:
                return QueryResponse(
                    intent="check_available_slots",
                    message=f"For {detected_sport} on {detected_date}, available slots are: {slot_str}. Which slot would you like to book?",
                    success=True,
                    suggested_slots=slots
                )
            else:
                return QueryResponse(
                    intent="check_available_slots",
                    message=f"Available slots for {detected_sport} on {detected_date}: {slot_str}. If you would like to book any slot, just say 'Book <slot>'.",
                    success=True,
                    pending_confirmation=False,
                    suggested_slots=slots
                )

        # Case B: Specific slot is specified -> check slot availability
        avail = tools.check_availability(detected_sport, detected_date, detected_slot)
        if avail["available"]:
            fac_name = avail["facility_name"]
            if is_explicit_book_action:
                # User asked to book -> arm confirmation
                session["pending_action"] = {
                    "type": "book_slot",
                    "sport_name": detected_sport,
                    "facility_id": avail["facility_id"],
                    "facility_name": fac_name,
                    "booking_date": detected_date,
                    "time_slot": detected_slot,
                    "timestamp": datetime.now()
                }
                msg = f"{fac_name} ({detected_sport}) is available on {detected_date} from {detected_slot}. Shall I confirm this booking?"
                return QueryResponse(
                    intent="confirm_booking_request",
                    message=msg,
                    success=True,
                    pending_confirmation=True,
                    data=avail
                )
            else:
                # User asked for availability -> Inform availability and arm pending availability_followup intent
                session["pending_action"] = {
                    "type": "availability_followup",
                    "sport_name": detected_sport,
                    "facility_id": avail["facility_id"],
                    "facility_name": fac_name,
                    "booking_date": detected_date,
                    "time_slot": detected_slot,
                    "timestamp": datetime.now()
                }
                msg = f"✅ {fac_name} ({detected_sport}) is available on {detected_date} at {detected_slot}. If you would like to book it, please say 'Yes' or 'Book it'."
                return QueryResponse(
                    intent="check_slot_availability",
                    message=msg,
                    success=True,
                    pending_confirmation=False,
                    data=avail
                )
        else:
            alt_slots = avail.get("alternative_slots", [])
            session["last_entities"]["available_slots"] = alt_slots
            if alt_slots:
                slot_str = ", ".join(alt_slots)
                msg = f"{detected_sport} is unavailable at {detected_slot} on {detected_date}. Available alternatives are: {slot_str}. Which one would you prefer?"
            else:
                msg = f"No alternative slots are currently available for {detected_sport} on {detected_date}."
            
            return QueryResponse(
                intent="slot_conflict_alternatives",
                message=msg,
                success=False,
                suggested_slots=alt_slots
            )

    # --- 15. GEMINI FUNCTION CALLING / FALLBACK ---
    return handle_gemini_or_smart_fallback(raw_query, current_user, session)

def handle_gemini_or_smart_fallback(query: str, current_user: Dict[str, Any], session: Dict[str, Any]) -> QueryResponse:
    """Invokes Gemini LLM if key is configured, or provides context-aware campus answers in English."""
    user_name = current_user.get("name", "User")
    user_role = current_user.get("role", "student")

    if GEMINI_API_KEY and GEMINI_API_KEY.strip():
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY.strip()}"
            system_prompt = (
                f"You are the Campus Sports ERP AI Assistant. Logged in user: {user_name} (Role: {user_role}). "
                "Help with facility information, campus sports rules, booking guidance, and query interpretation. "
                "Always respond in professional English."
            )
            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": f"System Instructions: {system_prompt}\nUser Query: {query}"}]
                    }
                ]
            }
            resp = requests.post(url, json=payload, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return QueryResponse(
                    intent="gemini_ai_response",
                    message=text,
                    success=True,
                    data={"source": "Google Gemini"}
                )
        except Exception:
            pass

    q = query.lower()
    if "rule" in q or "niti" in q or "equip" in q or "dress" in q or "shoes" in q:
        msg = (
            "Campus Sports Rules & Guidelines:\n"
            "1. Badminton & Basketball: Non-marking gum rubber shoes are strictly mandatory.\n"
            "2. Swimming Pool: Proper swimming costume and silicone cap are required.\n"
            "3. Timing: Facilities remain open from 06:00 AM to 09:00 PM daily.\n"
            "4. Check-in: Please mark attendance at the sports desk upon arrival."
        )
    else:
        msg = (
            "I can help you with bookings, availability, attendance, sports, facilities, and other Sports ERP tasks. "
            "Please tell me what you would like to do (e.g. 'Show my bookings', 'Book a badminton slot tomorrow at 5 PM', 'Show my attendance', or 'What sports are available?')."
        )

    return QueryResponse(
        intent="general_assistance",
        message=msg,
        success=True
    )
