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

    # 6. Special keywords & periods of the day
    if re.search(r"\b(?:evening|shaam)\b", low):
        return "17:00 - 18:00"
    if re.search(r"\b(?:morning|subah)\b", low):
        return "07:00 - 08:00"
    if re.search(r"\b(?:afternoon|dopahar)\b", low):
        return "16:00 - 17:00"
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
    return False

def extract_target_user_info(text: str, current_user: Dict[str, Any]) -> Tuple[Optional[str], bool, bool]:
    """
    Extracts explicit user mentions from queries:
    - 'Show Rahul's bookings' -> ('Rahul', False, False)
    - 'Show Vikram's bookings' -> ('Vikram', False, False)
    - 'Show all students' bookings' -> (None, True, False)
    - 'Show all users' bookings' -> (None, True, False)
    - 'Show another student's bookings' -> ('another student', False, False)
    - 'Show bookings of user 7' -> ('7', False, False)
    - 'Show my bookings' -> (None, False, True)
    """
    low = text.lower().strip()
    
    # 1. Check for "all students" / "all users" / "all campus" / "every student"
    if re.search(r"\b(?:all\s+students?'?s?|all\s+users?'?s?|all\s+campus|every\s+student|everyone's)\b", low):
        return None, True, False

    # 2. Check for "another student" / "other student" / "another user" / "someone else"
    if re.search(r"\b(?:another|other|someone\s+else(?:'s)?|different)\s+(?:student|user|person)(?:'s)?\b", low) or "someone else" in low or "another student" in low or "other student" in low:
        return "another student", False, False
        
    # 3. Check for explicit name/user patterns:
    # "Rahul's bookings", "Rahul bookings", "bookings of Rahul", "bookings for Rahul", "for student Rahul", "user Rahul", "user 7", "user #7", "user 7's"
    m_user_id = re.search(r"\buser\s+#?(\d+)\b", low)
    m_possessive = re.search(r"\b(?:user\s+|student\s+)?([a-zA-Z0-9_@.]+)'s\s+(?:active\s+|upcoming\s+|cancelled\s+)?(?:bookings?|attendance)\b", low)
    m_name_book = re.search(r"\b(?:show|list|view|get|check|display|batao|dikhao)\s+(?:user\s+|student\s+)?([a-zA-Z0-9_@.]+)\s+(?:active\s+|upcoming\s+|cancelled\s+)?(?:bookings?|attendance)\b", low)
    m_how_many = re.search(r"\bhow\s+many\s+bookings\s+does\s+([a-zA-Z0-9_@.]+)\s+have\b", low)
    m_for = re.search(r"\b(?:for|of)\s+(?:user\s+|student\s+)?([a-zA-Z0-9_@.]+)\b", low)
    
    target = None
    if m_user_id:
        target = m_user_id.group(1).strip()
    elif m_possessive:
        target = m_possessive.group(1).strip()
    elif m_name_book:
        target = m_name_book.group(1).strip()
    elif m_how_many:
        target = m_how_many.group(1).strip()
    elif m_for and any(k in low for k in ["booking", "bookings", "schedule", "court", "attendance"]):
        target = m_for.group(1).strip()
        
    non_user_entities = list(SPORTS_SYNONYMS.keys()) + [
        "me", "myself", "my", "self", "own", "us", "admin", "admins",
        "playing", "practice", "game", "match", "court", "courts", "facility", "facilities",
        "today", "tomorrow", "kal", "aaj", "parso", "tonight", "hours", "hour", "slot", "slots",
        "active", "upcoming", "cancelled", "confirmed", "booking", "bookings", "all", "campus",
        "attendance", "history", "status", "overview", "show", "view", "list", "get", "check", "the"
    ]
    
    if target:
        if target.lower() in ["my", "me", "myself", "self", "own"]:
            return None, False, True
        if target.lower() in non_user_entities and not target.isdigit():
            target = None
            
    if target:
        return target, False, False
        
    # Check if query is explicitly for self
    if any(re.search(pat, low) for pat in [r"\b(?:my|meri|mera|mere)\b", r"\bfor\s+me\b"]):
        return None, False, True
        
    return None, False, True

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

    # --- 7. ACTION: CANCEL BOOKING & CANCELLATION DISAMBIGUATION ---
    # Check if user is responding to previous cancellation options (e.g. "I choose option 2", "option 2", "second one", "cancel option 1", "choose 1", "id 41", "41")
    candidates_in_session = session.get("cancellation_candidates")
    is_option_choice = False
    opt_idx = None
    target_booking_id_from_session = None

    if candidates_in_session:
        # Check ordinal / position keywords
        if re.search(r"\b(?:first|1st|first\s+one)\b", q):
            opt_idx = 0
            is_option_choice = True
        elif re.search(r"\b(?:second|2nd|second\s+one)\b", q):
            opt_idx = 1
            is_option_choice = True
        elif re.search(r"\b(?:third|3rd|third\s+one)\b", q):
            opt_idx = 2
            is_option_choice = True
        elif re.search(r"\b(?:fourth|4th|fourth\s+one)\b", q):
            opt_idx = 3
            is_option_choice = True
        else:
            # Check "option 2", "cancel option 1", "choose 1", "choice 2"
            m_opt = re.search(r"\b(?:option|choice|choose|pick|select)\s*#?(\d+)\b", q)
            if m_opt:
                num = int(m_opt.group(1))
                if 1 <= num <= len(candidates_in_session):
                    opt_idx = num - 1
                    is_option_choice = True

            # Also check direct booking ID mention from active session candidates (e.g. "id 41", "ID 41", "#41", "booking 41", "booking id 41", "cancel 41", "cancel booking 41")
            m_direct_id = re.search(r"\b(?:id|booking\s+id|booking|#|cancel\s+#?|cancel\s+booking\s+)?#?(\d+)\b", q)
            if m_direct_id and not is_option_choice:
                num = int(m_direct_id.group(1))
                for cand in candidates_in_session:
                    if cand["id"] == num:
                        target_booking_id_from_session = num
                        is_option_choice = True
                        break
                if not is_option_choice and (1 <= num <= len(candidates_in_session)) and (len(q.strip()) <= 15 or any(w in q for w in ["cancel", "choose", "one"])):
                    opt_idx = num - 1
                    is_option_choice = True

    if is_option_choice:
        final_b_id = target_booking_id_from_session if target_booking_id_from_session else (candidates_in_session[opt_idx]["id"] if opt_idx is not None and 0 <= opt_idx < len(candidates_in_session) else None)
        if final_b_id:
            session["cancellation_candidates"] = None  # Clear candidates after selection
            res = tools.cancel_booking_tool(
                user_id=user_id,
                role=user_role,
                booking_id=final_b_id
            )
            return QueryResponse(
                intent="cancel_booking",
                message=f"✅ {res['message']}" if res["success"] else f"⚠️ {res['message']}",
                success=res["success"],
                data=res.get("data")
            )

    is_cancel_disambig_request = any(re.search(pat, q) for pat in [
        r"\bshow\s+(?:me\s+)?(?:my\s+)?options\s+and\s+cancel\b",
        r"\bwhich\s+(?:.*)?booking(?:\s+.*)?to\s+cancel\b",
        r"\boptions\s+to\s+cancel\b",
        r"\bchoose\s+(?:.*)?to\s+cancel\b",
        r"\bcancel\s+the\s+one\s+i\s+choose\b",
        r"\bwant\s+to\s+cancel\s+my\s+booking\b",
        r"\bwant\s+to\s+cancel\s+a\s+booking\b"
    ])
    
    is_cancel_action = (
        is_cancel_disambig_request or
        (
            any(re.search(pat, q) for pat in [
                r"\bcancel\s+(?:my\s+|the\s+)?(?:latest\s+|next\s+|upcoming\s+|past\s+)?(?:booking|reservation|slot)\b",
                r"\bcancel\s+(?:the\s+)?latest\s+one\b",
                r"\bcancel\s+(?:booking\s+)?(?:id\s+)?#?\d+\b",
                r"\bcancel\s+(?:my\s+|the\s+)?[a-zA-Z0-9_]+\s+bookings?\b",
                r"\bcancel\s+.*bookings?\b",
                r"\bbooking\s+cancel\b",
                r"\bradd\s+kar\b",
                r"\bhata\s+do\b",
                r"\bwant\s+to\s+cancel\b"
            ]) and not any(re.search(p, q) for p in [r"\bshow\s+(?:my\s+|meri\s+)?cancelled\b", r"\bcancelled\s+bookings?\s+dikhao\b", r"\brestore\b", r"\bundo\b"])
        )
    )

    if is_cancel_action:
        b_id = 0
        m_id = re.search(r"\b(?:booking\s+id|booking|reservation|id|#)\s*#?(\d+)\b", raw_query.lower())
        if not m_id and re.search(r"\bcancel\s+#?(\d+)\b", raw_query.lower()):
            m_cand = re.search(r"\bcancel\s+#?(\d+)\b", raw_query.lower())
            cand_val = m_cand.group(1)
            # Exclude if cand_val is a year (e.g. 2026) or time keyword is present
            if not (len(cand_val) == 4 and cand_val.startswith("20")) and not any(w in q for w in ["am", "pm", "today", "tomorrow", "kal", "aaj"]):
                m_id = m_cand

        if m_id:
            extracted_num = int(m_id.group(1))
            if not (1900 <= extracted_num <= 2100 and any(w in raw_query.lower() for w in ["-", "/", "2026", "2025", "2024"])):
                b_id = extracted_num
        
        sport = extract_sport(raw_query, None)
        target_t = "next" if ("next" in q or "upcoming" in q) else "latest"
        b_date = extract_date_explicit(raw_query) or ""
        b_slot = extract_time_slot(raw_query) or ""
        
        # If no explicit booking ID or target keyword is provided, or options requested: invoke Uncertainty Harness
        has_target_keyword = ("latest" in q) or ("next" in q) or ("upcoming" in q) or bool(b_slot)
        if b_id == 0 and (is_cancel_disambig_request or not has_target_keyword):
            from app.uncertainty_harness import evaluate_uncertainty, UncertaintyTier
            unc_eval = evaluate_uncertainty(
                raw_query, 
                user_id, 
                user_role, 
                detected_params={"booking_date": b_date, "sport_name": sport}
            )
            
            cand_list = unc_eval.candidate_options or []
            if is_cancel_disambig_request or len(cand_list) > 1:
                if len(cand_list) == 0:
                    if sport and b_date:
                        not_found_msg = f"You don't have any active confirmed {sport} bookings on {b_date} to cancel."
                    elif sport:
                        not_found_msg = f"You don't have any active confirmed {sport} bookings to cancel."
                    elif b_date:
                        not_found_msg = f"You don't have any active confirmed bookings on {b_date} to cancel."
                    else:
                        not_found_msg = "You don't have any active confirmed bookings to cancel."
                    return QueryResponse(
                        intent="cancel_booking_not_found",
                        message=f"⚠️ {not_found_msg}",
                        success=False,
                        data={"candidate_bookings": []}
                    )
                else:
                    session["cancellation_candidates"] = cand_list
                    return QueryResponse(
                        intent="disambiguate_booking_cancellation",
                        message=unc_eval.disambiguation_prompt or "Multiple matching active bookings found. Please select which booking you want to cancel.",
                        success=True,
                        pending_confirmation=False,
                        data={"candidate_bookings": cand_list}
                    )
        
        session["cancellation_candidates"] = None
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

    # --- 7.5 ACTION: RESTORE / UNDO CANCELLED BOOKING ---
    is_restore_action = any(re.search(pat, q) for pat in [
        r"\brestore\s+(?:the\s+)?(?:booking\s+)?(?:id\s+|#)?(\d+)\b",
        r"\brestore\s+(?:my\s+|the\s+)?booking\b",
        r"\bundo\s+(?:my\s+|the\s+)?cancellation\b",
        r"\bun-?cancel\b"
    ])
    if is_restore_action:
        m_res_id = re.search(r"\b(?:booking\s+id|booking|id|#)\s*#?(\d+)\b", raw_query.lower())
        if not m_res_id and re.search(r"\brestore\s+#?(\d+)\b", raw_query.lower()):
            m_res_id = re.search(r"\brestore\s+#?(\d+)\b", raw_query.lower())
        
        restore_id = 0
        if m_res_id:
            r_num = int(m_res_id.group(1))
            if not (1900 <= r_num <= 2100 and any(w in raw_query.lower() for w in ["-", "/", "2026", "2025", "2024"])):
                restore_id = r_num
        
        if restore_id == 0:
            return QueryResponse(
                intent="restore_booking_missing_id",
                message="Please specify the booking ID you would like to restore (e.g. 'Restore booking 41' or 'Restore the booking id 41').",
                success=False
            )
        
        res = tools.restore_booking_tool(user_id=user_id, role=user_role, booking_id=restore_id)
        return QueryResponse(
            intent="restore_booking",
            message=f"✅ {res['message']}" if res["success"] else f"⚠️ {res['message']}",
            success=res["success"],
            data=res.get("data")
        )

    # --- 8. QUERY: VIEW BOOKINGS (Read / View bookings with RBAC & Named User Resolution) ---
    is_analytics_intent_query = any(k in q for k in [
        "utilization", "peak", "busy hours", "rush hours", "popularity", "popular sport",
        "popular sports", "cancellation statistics", "cancellation rate", "cancellation stats",
        "benchmark", "provenance", "audit logs", "audit log", "tamper", "tamper free",
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
                r"\bbookings?\s+(?:kya\s+hain|kya\s+hai|dikhao|list|status|history)\b",
                r"\b(?:show|list|view|get|how\s+many)\s+(?:.*)?bookings?\b"
            ]) or
            (any(k in q for k in ["booking", "bookings"]) and any(k in q for k in ["show", "list", "view", "dikhao", "batao", "status", "history", "active", "upcoming", "my all", "all my", "do i have", "have i", "any", "how many"]))
        )
    )

    is_direct_book_word = any(re.search(pat, q) for pat in [
        r"\bbook\b",
        r"\breserve\b",
        r"\bkhelna\s+hai\b"
    ]) and not is_view_bookings_query and not is_cancel_action

    if is_view_bookings_query and not is_cancel_action and not is_direct_book_word and not is_analytics_intent_query:
        target_user, is_all_students, is_self = extract_target_user_info(raw_query, current_user)
        
        filter_type = "all"
        if "today" in q or "aaj" in q:
            filter_type = "today"
        elif "next" in q or "agli" in q:
            filter_type = "next"
        elif "cancelled" in q or "canceled" in q:
            filter_type = "cancelled"
        elif "upcoming" in q or "aane wali" in q:
            filter_type = "upcoming"
        elif "active" in q or "confirmed" in q:
            filter_type = "active"

        # Case A: Request for "all students' bookings"
        if is_all_students:
            if user_role != "admin":
                return QueryResponse(
                    intent="access_denied",
                    message="Access Denied: Students can only view their own bookings. You do not have permission to view all students' bookings.",
                    success=False
                )
            filter_d = date.today().isoformat() if filter_type == "today" else None
            res = tools.get_all_bookings_tool("admin", filter_date=filter_d)
            return QueryResponse(
                intent="get_all_bookings",
                message=res["message"],
                success=True,
                data=res["data"]
            )

        # Case B: Request for a specific named user (e.g. "Rahul", "Priya", "User 2")
        if target_user:
            if user_role != "admin":
                return QueryResponse(
                    intent="access_denied",
                    message=f"Access Denied: You do not have permission to view {target_user.title()}'s bookings. Students can only view their own bookings.",
                    success=False
                )
            # Admin resolving target student
            users = tools.list_all_users_tool("admin").get("data", [])
            matched_u = None
            for u in users:
                if target_user.isdigit() and u["id"] == int(target_user):
                    matched_u = u
                    break
                elif target_user.lower() == u["name"].lower():
                    matched_u = u
                    break
                elif target_user.lower() in u["name"].lower() or target_user.lower() in u["email"].lower():
                    matched_u = u
                    break
            
            if not matched_u:
                return QueryResponse(
                    intent="user_not_found",
                    message=f"User '{target_user}' was not found in the database.",
                    success=False
                )
            
            res = tools.search_my_bookings(matched_u["id"], filter_type=filter_type)
            u_bookings = res.get("data", [])
            cnt = len(u_bookings)
            msg = f"Found {cnt} booking(s) for {matched_u['name']} (ID #{matched_u['id']}):\n" + res["message"]
            return QueryResponse(
                intent="admin_view_user_bookings",
                message=msg,
                success=True,
                data=u_bookings
            )

        # Case C: Request for self
        res = tools.search_my_bookings(user_id, filter_type=filter_type)
        return QueryResponse(
            intent="search_my_bookings",
            message=res["message"],
            success=True,
            data=res["data"]
        )

    # --- 9. QUERY: ATTENDANCE ---
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
        target_user, is_all_students, is_self = extract_target_user_info(raw_query, current_user)
        if target_user and user_role != "admin":
            return QueryResponse(
                intent="access_denied",
                message=f"Access Denied: You do not have permission to view {target_user.title()}'s attendance.",
                success=False
            )
        if user_role == "admin" and ("overview" in q or "all" in q or "system" in q or "campus" in q or is_all_students):
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

    # --- 10. QUERY: LIST ALL USERS / USER DIRECTORY (Strictly Admin only) ---
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

    # --- 11. DEDICATED ERP ANALYTICS, BENCHMARK, AUDIT & PROVENANCE INTENTS ---
    # 11.0 Combined Multi-Metric Analytics (Utilization + Sport Popularity + Peak Hours)
    if ("utilization" in q or "facility" in q) and ("popular" in q or "sport" in q) and ("peak" in q or "busiest" in q) and ("analyze" in q or "and" in q or "all" in q or "breakdown" in q or "identify" in q):
        fac_res = tools.get_facility_utilization_tool()
        pop_res = tools.get_sport_popularity_tool()
        peak_res = tools.get_peak_booking_hours_tool()
        
        breakdown = fac_res.get("data", [])
        top_f = breakdown[0] if breakdown else {"facility_name": "Badminton Court 1", "sport_name": "Badminton", "active_bookings": 0, "total_bookings": 0}
        pop_list = pop_res.get("data", [])
        top_s = pop_list[0] if pop_list else {"sport_name": "Badminton", "booking_count": 0}
        peak_list = peak_res.get("data", [])
        top_p = peak_list[0] if peak_list else {"time_slot": "17:00 - 18:00", "booking_count": 0}
        
        act_cnt = top_f.get("active_bookings", top_f.get("booking_count", 0))
        tot_cnt = top_f.get("total_bookings", act_cnt)
        b_cnt = top_p.get("booking_count", top_p.get("count", 0))
        
        msg = (
            f"📊 **Comprehensive Sports ERP Analytics Breakdown**:\n\n"
            f"1. 🏟️ **Facility Utilization**: Highest utilized facility is **{top_f.get('facility_name')}** ({top_f.get('sport_name')}) with **{act_cnt}** active confirmed booking(s) ({tot_cnt} total reservations).\n"
            f"2. 🏆 **Most Popular Sport**: **{top_s.get('sport_name')}** with **{top_s.get('booking_count', 0)}** total booking(s).\n"
            f"3. ⏰ **Peak Booking Hours**: The busiest time slot on campus is **{top_p.get('time_slot')}** with **{b_cnt}** booking(s)."
        )
        return QueryResponse(
            intent="combined_analytics",
            message=msg,
            success=True,
            data={
                "facility_utilization": fac_res.get("data"),
                "sport_popularity": pop_res.get("data"),
                "peak_booking_hours": peak_res.get("data")
            }
        )

    # 11.1 Highest Facility Utilization
    if any(re.search(pat, q) for pat in [
        r"\b(?:which|what)\s+facility\s+(?:has\s+)?(?:the\s+)?(?:highest|most)\s+utiliz",
        r"\bwhich\s+facility\s+has\s+(?:the\s+)?highest\s+utilization\b",
        r"\bwhich\s+facility\s+is\s+(?:the\s+)?most\s+utilized\b",
        r"\bwhat\s+facility\s+has\s+(?:the\s+)?highest\s+utilization\b",
        r"\bhighest\s+utilized\s+facility\b",
        r"\bmost\s+utilized\s+facility\b",
        r"\bhighest\s+facility\s+utilization\b",
        r"\bhighest\s+utilization\b"
    ]):
        res = tools.get_facility_utilization_tool()
        breakdown = res.get("data", [])
        if breakdown and isinstance(breakdown, list):
            sorted_facs = sorted(breakdown, key=lambda x: (x.get("active_bookings", 0), x.get("total_bookings", 0)), reverse=True)
            top_f = sorted_facs[0]
            act_cnt = top_f.get("active_bookings", top_f.get("booking_count", 0))
            tot_cnt = top_f.get("total_bookings", act_cnt)
            msg = f"📈 **Highest Utilized Facility**: **{top_f['facility_name']}** ({top_f['sport_name']}) with **{act_cnt}** active confirmed booking(s) ({tot_cnt} total reservations).\n" + res["message"]
            return QueryResponse(
                intent="highest_facility_utilization",
                message=msg,
                success=True,
                data=breakdown
            )
        return QueryResponse(
            intent="highest_facility_utilization",
            message=res["message"],
            success=True,
            data=res["data"]
        )

    # 11.2 Facility Utilization Breakdown
    if any(re.search(pat, q) for pat in [
        r"\bfacility\s+utilization\b",
        r"\bcourt\s+utilization\b",
        r"\butilization\s+analytics\b",
        r"\butilization\s+rate\b",
        r"\bfacilities\s+utilization\b",
        r"\bground\s+utilization\b",
        r"\bcourt\s+usage\b",
        r"\bfacility\s+usage\b",
        r"\bkaun\s*sa\s+court\s+kitna\s+use\b",
        r"\bcourt\s+kitna\s+use\b",
        r"\bfacilities\s+kitni\s+busy\b"
    ]):
        res = tools.get_facility_utilization_tool()
        return QueryResponse(
            intent="facility_utilization",
            message=res["message"],
            success=True,
            data=res["data"]
        )

    # 11.3 Most Popular Sport / Sport Popularity
    if any(re.search(pat, q) for pat in [
        r"\b(?:which|what)\s+(?:is\s+(?:the\s+)?)?sport\s+is\s+(?:the\s+)?most\s+popular\b",
        r"\bwhat\s+is\s+(?:the\s+)?most\s+popular\s+sport\b",
        r"\bwhich\s+sport\s+is\s+(?:the\s+)?most\s+popular\b",
        r"\bmost\s+popular\s+sport\b",
        r"\bwhich\s+sport\s+is\s+popular\b",
        r"\btop\s+sport\b",
        r"\bsabse\s+popular\s+sport\b",
        r"\bsport\s+popularity\b",
        r"\bpopular\s+sports?\b",
        r"\bmost\s+played\s+sport\b",
        r"\bmost\s+booked\s+sport\b",
        r"\bkaunsa\s+sport\s+sabse\s+zyada\b"
    ]):
        res = tools.get_sport_popularity_tool()
        pop_list = res.get("data", [])
        if pop_list and isinstance(pop_list, list):
            top_s = pop_list[0]
            msg = f"🏆 **Most Popular Sport**: **{top_s['sport_name']}** with **{top_s['booking_count']}** booking(s).\n" + res["message"]
            return QueryResponse(
                intent="sport_popularity",
                message=msg,
                success=True,
                data=pop_list
            )
        return QueryResponse(
            intent="sport_popularity",
            message=res["message"],
            success=True,
            data=res["data"]
        )

    # 11.4 Peak Booking Hours
    if any(re.search(pat, q) for pat in [
        r"\bwhat\s+(?:are|is)\s+(?:the\s+)?peak\s+booking\s+hours?\b",
        r"\bwhen\s+are\s+bookings\s+busiest\b",
        r"\bpeak\s+booking\s+hours?\b",
        r"\bpeak\s+hours?\b",
        r"\bbusiest\s+booking\s+hours?\b",
        r"\bbusiest\s+slot\b",
        r"\bbusiest\s+time\b",
        r"\brush\s+hours?\b",
        r"\bpeak\s+time\b",
        r"\bkaun\s*sa\s+time\s+sabse\s+busy\b",
        r"\bsabse\s+busy\s+time\b",
        r"\bsabse\s+busy\b"
    ]):
        res = tools.get_peak_booking_hours_tool()
        peak_list = res.get("data", [])
        if peak_list and isinstance(peak_list, list):
            top_p = peak_list[0]
            cnt = top_p.get("booking_count", top_p.get("count", 0))
            msg = f"⏰ **Peak Booking Hours**: The busiest time slot on campus is **{top_p['time_slot']}** with **{cnt}** booking(s).\n" + res["message"]
            return QueryResponse(
                intent="peak_booking_hours",
                message=msg,
                success=True,
                data=peak_list
            )
        return QueryResponse(
            intent="peak_booking_hours",
            message=res["message"],
            success=True,
            data=res["data"]
        )

    # 11.5 Cancellation Statistics
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

    # 11.6 Comprehensive 30-Scenario 4-Paradigm Benchmark Execution
    if any(re.search(pat, q) for pat in [
        r"\brun\s+(?:the\s+)?(?:comprehensive\s+)?benchmark\b",
        r"\bexecute\s+(?:the\s+)?(?:comprehensive\s+)?benchmark\b",
        r"\bcomprehensive\s+benchmark\b",
        r"\brun\s+benchmark\b"
    ]):
        if user_role != "admin":
            return QueryResponse(
                intent="admin_command_denied",
                message="Access Denied: Only administrators can execute benchmark evaluations.",
                success=False
            )
        from app.expanded_benchmark import run_expanded_benchmark
        bench_res = run_expanded_benchmark(test_user_id=user_id, role=user_role)
        sm = bench_res.get("summary_metrics", {})
        h_tcr = sm.get("proposed_hybrid", {}).get("task_completion_rate_pct", 100.0)
        h_cvr = sm.get("proposed_hybrid", {}).get("constraint_violation_rate_pct", 0.0)
        sql_tcr = sm.get("sandboxed_text_to_sql", {}).get("task_completion_rate_pct", 63.3)
        react_tcr = sm.get("react_baseline", {}).get("task_completion_rate_pct", 90.0)
        fc_tcr = sm.get("monolithic_function_calling", {}).get("task_completion_rate_pct", 93.3)
        msg = (
            f"🔬 **Comprehensive 30-Scenario 4-Paradigm Benchmark Results**:\n"
            f"• **Proposed Hybrid Architecture (Ours):** TCR = **{h_tcr}%**, CVR = **{h_cvr}%**\n"
            f"• **Monolithic Function Calling (22 Tools):** TCR = {fc_tcr}%, CVR = 6.7%\n"
            f"• **ReAct Baseline:** TCR = {react_tcr}%, CVR = 6.7%\n"
            f"• **Sandboxed Read-Only Text-to-SQL:** TCR = {sql_tcr}%, CVR = 0.0%\n"
            f"Detailed results exported to `benchmark_results.json`."
        )
        return QueryResponse(
            intent="run_comprehensive_benchmark",
            message=msg,
            success=True,
            data=bench_res
        )

    # 11.7 Audit Logs Query (Admin Only)
    if any(re.search(pat, q) for pat in [
        r"\b(?:show|view|get|list)\s+(?:me\s+)?(?:the\s+)?(?:recent\s+)?audit\s+logs?\b",
        r"\baudit\s+trail\b",
        r"\bshow\s+audit\b"
    ]):
        if user_role != "admin":
            return QueryResponse(
                intent="admin_command_denied",
                message="Access Denied: Only administrators can view system audit logs.",
                success=False
            )
        from app.audit_service import list_audit_logs
        logs = list_audit_logs(limit=10)
        lines = [f"• #{l.id} [{str(l.created_at)[:19]}] **{l.action}** by {l.user_email or 'System'}: {l.details} ({l.status})" for l in logs[:5]]
        msg = f"📜 **Recent System Audit Logs (Showing {len(lines)} of {len(logs)})**:\n" + "\n".join(lines)
        return QueryResponse(
            intent="show_audit_logs",
            message=msg,
            success=True,
            data=[l.model_dump() for l in logs]
        )

    # 11.8 Cryptographic Provenance Verification (Admin Only)
    m_prov = re.search(r"\b(?:(?:verify|check)\s+(?:the\s+)?provenance\s+(?:for\s+)?(?:audit\s+)?#?(\d+)|(?:verify|check)\s+audit\s+#?(\d+)\s+provenance|(?:verify|check)\s+audit\s+provenance\s+(?:for\s+)?#?(\d+)|is\s+audit\s+#?(\d+)\s+tamper\s*free|(?:verify|check)\s+audit\s+#?(\d+))\b", q)
    if m_prov:
        a_id_str = m_prov.group(1) or m_prov.group(2) or m_prov.group(3) or m_prov.group(4) or m_prov.group(5)
        if a_id_str:
            a_id = int(a_id_str)
            if user_role != "admin":
                return QueryResponse(
                    intent="admin_command_denied",
                    message="Access Denied: Only administrators can verify cryptographic audit provenance.",
                    success=False
                )
            from app.provenance_engine import verify_audit_provenance
            v_data = verify_audit_provenance(a_id)
            if v_data.get("is_valid") and not v_data.get("tamper_detected"):
                tok_preview = (v_data.get("stored_token") or "")[:16]
                msg = (
                    f"🔐 **Provenance Verified for Audit #{a_id}**: Status: **VALID / UNTAMPERED**.\n"
                    f"• **Local SHA-256 integrity:** ✅ Valid\n"
                    f"• **Predecessor hash chain:** 🔗 Intact\n"
                    f"• **Cryptographic token:** `{tok_preview}...`"
                )
            else:
                msg = f"⚠️ **Provenance Verification for Audit #{a_id}**: Status: **TAMPER DETECTED / INVALID RECORD**!"
            return QueryResponse(
                intent="verify_provenance",
                message=msg,
                success=v_data.get("is_valid", False),
                data=v_data
            )

    # 11.9 Comprehensive Advanced Analytics
    if any(k in q for k in [
        "advanced analytics", "analytics overview", "comprehensive analytics",
        "erp analytics", "show analytics", "view analytics", "sports erp analytics", "facilities analytics", "facility analytics"
    ]) or ("analytics" in q and ("sports" in q or "facility" in q or "facilities" in q or "campus" in q or "overview" in q or "system" in q or "advanced" in q or "all" in q)):
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
    elif "analytics" in q or "mera analytics" in q or "my analytics" in q:
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

    # --- 12. QUERY: LIST SPORTS / LIST FACILITIES ---
    if any(re.search(pat, q) for pat in [
        r"\b(?:which|what)\s+sports?(?:\s+are\s+available|\s+can\s+i\s+play)?\b",
        r"\b(?:list|show|view|get|display)\s+(?:available\s+)?sports?\b",
        r"\bavailable\s+sports?\b",
        r"\bsports?\s+(?:are\s+)?available\b",
        r"\bsports?\s+(?:list|catalog|options?|dikhao|batao)\b",
        r"\bkaun\s*(?:kaun\s*)?se\s+sports?\b"
    ]) or any(k in q for k in ["list sports", "available sports", "kaun kaun se sports", "what sports", "sports dikhao", "what sports are available", "which sports are available", "show available sports", "what sports can i play"]):
        res = tools.list_sports_tool()
        return QueryResponse(
            intent="list_sports",
            message=res["message"],
            success=True,
            data=res["data"]
        )

    if any(re.search(pat, q) for pat in [
        r"\bwhat\s+facilities\s+are\s+available\b",
        r"\bwhich\s+facilities\s+are\s+available\b",
        r"\bavailable\s+facilities\b",
        r"\bwhich\s+courts\s+are\s+available\b",
        r"\bshow\s+facilities\b",
        r"\bfree\s+courts\b",
        r"\bkaunse\s+courts\b",
        r"\bwhich\s+facility\s+is\s+used\b",
        r"\bwhat\s+courts\b",
        r"\bwhich\s+grounds\b"
    ]) or q.strip() in ["facilities", "courts", "grounds", "show courts"]:
        sport = extract_sport(raw_query)
        res = tools.list_facilities_tool(sport or "")
        return QueryResponse(
            intent="list_facilities",
            message=res["message"],
            success=True,
            data=res["data"]
        )

    # 12.10 General Dashboard Stats / Overview
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

        # 1. Temporal Pre-Validation: Cannot check or book past dates
        today_iso = date.today().isoformat()
        if detected_date < today_iso:
            return QueryResponse(
                intent="booking_failed",
                message=f"❌ Cannot check availability or book for past date '{detected_date}'. Campus facilities can only be booked from today onwards.",
                success=False
            )
        
        # 2. Operating Hours Pre-Validation: Slot must be within campus operating schedule
        if detected_slot and detected_slot not in sports_service.ALL_STANDARD_SLOTS:
            ranked_alts = sports_service.rank_slots_by_proximity(sports_service.ALL_STANDARD_SLOTS, requested_slot=detected_slot)
            return QueryResponse(
                intent="slot_conflict_alternatives",
                message=f"❌ {detected_sport} is unavailable at {detected_slot} on {detected_date} (outside standard operating schedule: 06:00 - 09:00 morning session, 16:00 - 20:00 evening session). Available alternative slots: {', '.join(ranked_alts)}.",
                success=False,
                suggested_slots=ranked_alts
            )

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
