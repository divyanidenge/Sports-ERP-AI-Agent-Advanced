import re
import json
import requests
from datetime import date, timedelta
from typing import Dict, Any, Optional, List, Tuple
from app.config import GEMINI_API_KEY
from app.models import QueryResponse
import app.agent_tools as tools

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
                "time_slot": None
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
    "swimming": "Swimming",
    "swim": "Swimming",
    "pool": "Swimming",
    "table tennis": "Table Tennis",
    "tt": "Table Tennis",
    "ping pong": "Table Tennis",
    "pingpong": "Table Tennis",
    "tennis": "Tennis",
    "volleyball": "Volleyball",
    "squash": "Squash"
}

TIME_SLOT_PATTERNS = [
    # 06:00 - 07:00
    (r"\b(?:0?6:00\s*(?:-|to)\s*0?7:00)\b|\b(?:6|06)\s*(?:-|to)\s*(?:7|07)\s*am\b|\b(?:6|06)\s*(?:am|subah)\b|\b06:00\b|\b6\s*baje\s*subah\b|\bsubah\s*6\s*baje\b", "06:00 - 07:00"),
    # 07:00 - 08:00
    (r"\b(?:0?7:00\s*(?:-|to)\s*0?8:00)\b|\b(?:7|07)\s*(?:-|to)\s*(?:8|08)\s*am\b|\b(?:7|07)\s*(?:am|subah)\b|\b07:00\b|\b7\s*baje\s*subah\b|\bsubah\s*7\s*baje\b", "07:00 - 08:00"),
    # 08:00 - 09:00
    (r"\b(?:0?8:00\s*(?:-|to)\s*0?9:00)\b|\b(?:8|08)\s*(?:-|to)\s*(?:9|09)\s*am\b|\b(?:8|08)\s*(?:am|subah)\b|\b08:00\b|\b8\s*baje\s*subah\b|\bsubah\s*8\s*baje\b", "08:00 - 09:00"),
    # 16:00 - 17:00 (4 PM - 5 PM)
    (r"\b(?:16:00\s*(?:-|to)\s*17:00)\b|\b(?:4|04|16)\s*(?:-|to)\s*(?:5|05|17)\s*(?:pm|shaam|evening)?\b|\b(?:4|04)\s*(?:pm|shaam|evening)\b|\b16:00\b|\b4\s*baje\s*(?:shaam|pm)?\b|\bshaam\s*4\s*baje\b", "16:00 - 17:00"),
    # 17:00 - 18:00 (5 PM - 6 PM)
    (r"\b(?:17:00\s*(?:-|to)\s*18:00)\b|\b(?:5|05|17)\s*(?:-|to)\s*(?:6|06|18)\s*(?:pm|shaam|evening)?\b|\b(?:5|05)\s*(?:pm|shaam|evening)\b|\b17:00\b|\b5\s*baje\b|\bshaam\s*5\s*baje\b|\b5pm\b|\b5\s*pm\b", "17:00 - 18:00"),
    # 18:00 - 19:00 (6 PM - 7 PM)
    (r"\b(?:18:00\s*(?:-|to)\s*19:00)\b|\b(?:6|06|18)\s*(?:-|to)\s*(?:7|07|19)\s*(?:pm|shaam|evening)?\b|\b(?:6|06)\s*(?:pm|shaam|evening)\b|\b18:00\b|\b6\s*baje\s*(?:shaam|pm)?\b|\bshaam\s*6\s*baje\b|\b6pm\b|\b6\s*pm\b", "18:00 - 19:00"),
    # 19:00 - 20:00 (7 PM - 8 PM)
    (r"\b(?:19:00\s*(?:-|to)\s*20:00)\b|\b(?:7|07|19)\s*(?:-|to)\s*(?:8|08|20)\s*(?:pm|shaam|evening|night)?\b|\b(?:7|07)\s*(?:pm|shaam|evening)\b|\b19:00\b|\b7\s*baje\s*(?:shaam|pm)?\b|\bshaam\s*7\s*baje\b|\b7pm\b|\b7\s*pm\b|\b8\s*pm\b|\b8pm\b|\b20:00\b", "19:00 - 20:00"),
]

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
    low = text.lower()
    for pat, slot in TIME_SLOT_PATTERNS:
        if re.search(pat, low):
            return slot
    return fallback_slot

def is_affirmation(text: str) -> bool:
    low = text.lower().strip()
    affirmative = [
        "yes", "haan", "ha", "haa", "kar do", "kardo", "confirm", "ok", "sure",
        "yup", "yeah", "book it", "block it", "proceed", "done", "theek hai", "chalega", "yes please"
    ]
    if low in ["y", "yes", "haan", "ha", "haa", "yes.", "haanji", "han", "ok", "confirm", "sure", "book it", "proceed"]:
        return True
    return any(re.search(rf"^(?:{re.escape(w)})$", low) for w in affirmative) or any(re.search(rf"\b{re.escape(w)}\b", low) for w in ["kar do", "kardo", "book it", "confirm it", "proceed"])

def is_negation(text: str) -> bool:
    low = text.lower().strip()
    negative = ["no", "nahi", "nahin", "mat karo", "cancel", "nope", "nevermind", "dont", "don't", "cancel action"]
    if low in ["n", "no", "nahi", "nahin", "no.", "nope", "cancel", "mat karo"]:
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
        if is_affirmation(q):
            action_type = pending.get("type")
            session["pending_action"] = None # Clear pending state

            if action_type == "book_slot":
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
                        message="Permission Denied: You don't have permission to perform this action.",
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
                        message="Permission Denied: You don't have permission to perform this action.",
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

    # --- 2. USER IDENTITY QUERY ("Who am I logged in as?") ---
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
        r"\bwhom\s+am\s+i\b"
    ]
    if any(re.search(pat, q) for pat in identity_patterns):
        session["last_entities"] = {"sport": None, "date": None, "time_slot": None}
        return QueryResponse(
            intent="who_am_i",
            message=f"You are currently logged in as **{user_name}**, {user_role.title()} ({user_email}).",
            success=True,
            data={"name": user_name, "role": user_role, "email": user_email, "id": user_id}
        )

    # --- 3. USER ROLE QUERY ("Am I a student or admin?", "Mera role kya hai?", "Which role do I have?") ---
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
        r"\bwho\s+role\b",
        r"\brole\b"
    ]
    if any(re.search(pat, q) for pat in role_patterns):
        session["last_entities"] = {"sport": None, "date": None, "time_slot": None}
        return QueryResponse(
            intent="user_role_info",
            message=f"Your current system role is **{user_role.title()}**.",
            success=True,
            data={"role": user_role}
        )

    # --- 4. CATALOG QUERY ("show catalog", "show my catalog", "sports catalog") ---
    if any(re.search(rf"\b{re.escape(k)}\b", q) for k in [
        "catalog", "show catalog", "show my catalog", "sports catalog", "facilities catalog",
        "view catalog", "list catalog", "all catalog", "sports and facilities"
    ]):
        session["last_entities"] = {"sport": None, "date": None, "time_slot": None}
        sports_res = tools.list_sports_tool()
        fac_res = tools.list_facilities_tool()
        sports_list = sports_res.get("data", [])
        fac_list = fac_res.get("data", [])
        
        sport_names = ", ".join([s["name"] for s in sports_list])
        msg = (
            f"🏅 **Campus Sports Catalog**:\n"
            f"• **Available Sports ({len(sports_list)}):** {sport_names}\n"
            f"• **Active Facilities ({len(fac_list)}):** {len(fac_list)} courts, fields & pools available on campus.\n"
            f"You can explore full details in the Sports & Facilities tabs, or ask me *'Kal 5 PM badminton available hai?'* to check slots!"
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
            "target_name": user_info["name"]
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
    # Students cannot book on behalf of another user
    is_third_party_book = re.search(r"\bfor\s+(?:user\s+)?([a-zA-Z0-9_@.]+)\b", q)
    non_user_entities = list(SPORTS_SYNONYMS.keys()) + [
        "me", "myself", "my", "self", "own", "us", "student", "students", "admin",
        "playing", "practice", "game", "match", "court", "courts", "facility", "facilities",
        "today", "tomorrow", "kal", "aaj", "parso", "tonight", "hours", "hour", "slot", "slots",
        "badminton", "cricket", "football", "basketball", "swimming", "tennis",
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

    # --- 7. QUERY: ADMIN CAMPUS-WIDE BOOKINGS ---
    admin_bookings_patterns = [
        r"\b(?:show\s+|list\s+|view\s+)?(?:today'?s|todays|today|aaj\s+ki)\s+bookings?\b",
        r"\b(?:show\s+|list\s+|view\s+)?all\s+(?:campus\s+)?bookings?\b",
        r"\b(?:all\s+|campus\s+)bookings?\b",
        r"\bfacility\s+bookings?\b"
    ]
    if user_role == "admin" and any(re.search(pat, q) for pat in admin_bookings_patterns):
        filter_d = date.today().isoformat() if any(k in q for k in ["today", "todays", "today's", "aaj"]) else None
        res = tools.get_all_bookings_tool("admin", filter_date=filter_d)
        return QueryResponse(
            intent="get_all_bookings",
            message=res["message"],
            success=True,
            data=res["data"]
        )

    # --- 8. QUERY: STUDENT BOOKINGS (Read / View bookings) ---
    is_view_bookings_query = (
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
        (any(k in q for k in ["booking", "bookings"]) and any(k in q for k in ["show", "list", "view", "dikhao", "batao", "kya hai", "kya hain", "status", "history", "active", "upcoming", "my all", "all my", "do i have", "have i", "any"]))
    )
    is_cancel_action = (
        any(re.search(pat, q) for pat in [
            r"\bcancel\s+(?:my\s+|the\s+)?booking\b",
            r"\bcancel\s+(?:my\s+)?(?:reservation|slot)\b",
            r"\bcancel\s+(?:booking\s+)?(?:id\s+)?#?\d+\b",
            r"\bbooking\s+cancel\b",
            r"\bradd\s+kar\b",
            r"\bhata\s+do\b"
        ]) and not any(k in q for k in ["show", "list", "view", "dikhao", "batao", "history"])
    )
    is_direct_book_word = any(re.search(pat, q) for pat in [
        r"\bbook\b",
        r"\breserve\b",
        r"\bkhelna\s+hai\b"
    ]) and not is_view_bookings_query

    if is_view_bookings_query and not is_cancel_action and not is_direct_book_word:
        filter_type = "all"
        if "today" in q or "aaj" in q:
            filter_type = "today"
        elif "next" in q or "agli" in q:
            filter_type = "next"
        elif "cancelled" in q or "canceled" in q:
            filter_type = "cancelled"
        elif "upcoming" in q or "aane wali" in q or "active" in q:
            filter_type = "upcoming"

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
        r"\battendance\s+(?:percentage|rate|summary|dikhao|batao|kitni\s+hai|kya\s+hai)\b",
        r"\b(?:how\s+many\s+)?sessions?\s+(?:have\s+i\s+)?attended\b",
        r"\bcheck\s*in\s*records?\b",
        r"\battended\b",
        r"\bmissed\s+sessions?\b"
    ]
    if any(re.search(pat, q) for pat in attendance_patterns) or any(k in q for k in ["attendance", "meri attendance"]):
        session["last_entities"] = {"sport": None, "date": None, "time_slot": None}
        if user_role == "admin" and ("overview" in q or "all" in q or "system" in q or "campus" in q):
            res = tools.get_dashboard_stats_tool()
            return QueryResponse(
                intent="get_dashboard_stats",
                message=f"Campus Attendance Overview: Overall check-in attendance rate is {res.get('data', {}).get('attendance_rate', 100)}%.",
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
        session["last_entities"] = {"sport": None, "date": None, "time_slot": None}
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

    # --- 11. QUERY: LIST SPORTS / LIST FACILITIES ---
    if any(k in q for k in ["list sports", "available sports", "kaun kaun se sports", "what sports", "sports dikhao", "what sports are available"]):
        session["last_entities"] = {"sport": None, "date": None, "time_slot": None}
        res = tools.list_sports_tool()
        return QueryResponse(
            intent="list_sports",
            message=res["message"],
            success=True,
            data=res["data"]
        )

    if any(k in q for k in ["what facilities are available", "which facilities are available", "facilities", "courts", "grounds", "kaunse courts", "free courts", "available facilities", "show facilities", "which courts are free today"]):
        session["last_entities"] = {"sport": None, "date": None, "time_slot": None}
        sport = extract_sport(raw_query)
        res = tools.list_facilities_tool(sport or "")
        return QueryResponse(
            intent="list_facilities",
            message=res["message"],
            success=True,
            data=res["data"]
        )

    # --- 12. QUERY: OVERVIEW / STATS ---
    if any(k in q for k in ["overview", "dashboard", "summary", "stats", "statistics", "report", "sports erp overview"]):
        session["last_entities"] = {"sport": None, "date": None, "time_slot": None}
        res = tools.get_dashboard_stats_tool()
        return QueryResponse(
            intent="get_dashboard_stats",
            message=res["message"],
            success=True,
            data=res["data"]
        )

    # --- 13. ACTION: CANCEL BOOKING ---
    if is_cancel_action or any(k in q for k in ["cancel my booking", "cancel booking", "booking cancel kar", "booking cancel karo", "cancel reservation", "cancel latest booking", "meri latest booking cancel", "meri booking cancel"]):
        session["last_entities"] = {"sport": None, "date": None, "time_slot": None}
        # Extract ID if present
        b_id = 0
        m = re.search(r"\b(?:id|booking|#)\s*#?(\d+)\b", raw_query.lower())
        if m:
            b_id = int(m.group(1))
        
        sport = extract_sport(raw_query, None)
        res = tools.cancel_booking_tool(user_id=user_id, role=user_role, sport_name=sport or "", booking_id=b_id)
        return QueryResponse(
            intent="cancel_booking",
            message=f"✅ {res['message']}" if res["success"] else f"⚠️ {res['message']}",
            success=res["success"],
            data=res.get("data")
        )

    # --- 14. ACTION: BOOKING & AVAILABILITY FLOW ---
    # Distinguish between explicit booking action and read-only availability inquiry
    is_explicit_book_action = (
        any(re.search(pat, q) for pat in [
            r"\bbook\b",
            r"\breserve\b",
            r"\bkhelna\s+hai\b",
            r"\bslot\s+chahiye\b",
            r"\bslot\s+book\b",
            r"\bbook\s+(?:a\s+)?court\b"
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
        r"\bavailable\s+slots?\b"
    ])
    
    sport_in_query = extract_sport(raw_query, None)
    slot_in_query = extract_time_slot(raw_query, None)
    date_in_query = extract_date_explicit(raw_query)

    should_run_booking_or_avail = is_explicit_book_action or is_avail_query or (sport_in_query and slot_in_query) or (slot_in_query and session["last_entities"].get("sport"))

    if should_run_booking_or_avail:
        detected_sport = sport_in_query or session["last_entities"].get("sport")
        detected_date = date_in_query or session["last_entities"].get("date") or (date.today() + timedelta(days=1)).isoformat()
        
        if is_avail_query or not is_explicit_book_action:
            detected_slot = slot_in_query
        else:
            detected_slot = slot_in_query or session["last_entities"].get("time_slot")

        if not detected_sport:
            return QueryResponse(
                intent="missing_sport",
                message="Which sport would you like to check or book? (e.g. Badminton, Cricket, Football, Basketball, Swimming, Table Tennis)",
                success=True
            )
        
        session["last_entities"]["sport"] = detected_sport
        session["last_entities"]["date"] = detected_date
        session["last_entities"]["time_slot"] = detected_slot
        if detected_slot:
            session["last_entities"]["time_slot"] = detected_slot

        # Case A: Slot is not specified -> list all available slots from real SQLite DB
        if not detected_slot:
            alt = tools.find_alternative_slots(detected_sport, detected_date)
            slots = alt.get("available_slots", [])
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
                    "time_slot": detected_slot
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
                # User just asked for availability -> Inform only, do NOT arm confirmation
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
            if alt_slots:
                slot_str = ", ".join(alt_slots)
                msg = f"{detected_sport} is already booked at {detected_slot} on {detected_date}. I found these available alternative slots: {slot_str}. Which one would you prefer?"
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
    """Invokes Gemini LLM if key is configured, or provides context-aware campus answers."""
    user_name = current_user.get("name", "User")
    user_role = current_user.get("role", "student")

    if GEMINI_API_KEY and GEMINI_API_KEY.strip():
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY.strip()}"
            system_prompt = (
                f"You are the Campus Sports ERP AI Assistant. Logged in user: {user_name} (Role: {user_role}). "
                "Help with facility information, campus sports rules, booking guidance, and query interpretation. "
                "Keep responses polite, natural, and helpful in English or Hinglish as requested."
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
    elif "help" in q or "madad" in q or "kya kar sakte ho" in q:
        msg = (
            f"Hello {user_name}! Main aapka Sports ERP AI Assistant hoon. Aap mujhse pooch sakte hain:\n"
            "• 'Kal 5 PM badminton book kar do'\n"
            "• 'Meri active bookings kya hain?'\n"
            "• 'Who am I logged in as?'\n"
            "• 'Am I a student or admin?'\n"
            "• 'Show catalog'\n"
            "• 'Badminton ka koi available slot kal batao'\n"
            "• 'Mere kitne attendance hain?'\n"
            "• 'Show overview'\n"
            + ("• 'Rahul ko block kar do' (Admin only)\n" if user_role == "admin" else "")
        )
    else:
        msg = (
            f"Hello {user_name}! Main aapki sports booking aur campus facilities mein madad kar sakta hoon. "
            "Aap 'Kal 5 PM badminton book kar do', 'Meri bookings dikhao', 'Who am I logged in as?', ya 'Show catalog' try kar sakte hain."
        )

    return QueryResponse(
        intent="general_assistance",
        message=msg,
        success=True
    )
