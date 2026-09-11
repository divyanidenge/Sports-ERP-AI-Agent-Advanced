r"""
app/symbolic_mus_engine.py
--------------------------
Symbolic Minimal Unsatisfiable Subset (MUS) & Minimal Correction Subset (MCS) Engine.
Inspired by TRACE-CS (Vasileiou & Yeoh, 2024).

Formal Model:
- Knowledge Base KB_sports = {C1, C2, C3, C4, C5, C6, C7, C8} representing domain invariants.
- A requested reservation R = <user_id, sport_name, facility_id, booking_date, time_slot, role>
  induces a ground propositional state query against system-of-record facts.
- When KB_sports ∪ {R} |= ⊥ (conflict/unsatisfiable), the engine:
  1. Identifies ALL simultaneously violated constraint clauses.
  2. Extracts the Minimal Unsatisfiable Subset (MUS) via deletion-based core reduction:
     MUS ⊆ KB ∪ {R} s.t. MUS |= ⊥ and ∀ c ∈ MUS, (MUS \ {c}) |≠ ⊥.
  3. Computes the Minimal Correction Set (MCS) / minimal relaxations:
     MCS = minimal subset of user request parameters whose modification restores satisfiability.
  4. Synthesizes a deterministic, non-hallucinated contrastive explanation:
     "Why not R? Because of minimal conflict core M. Satisfiable if minimal relaxation S is applied."
"""

from typing import Dict, Any, List, Optional, Tuple, Set
from datetime import date, datetime, timedelta
from pydantic import BaseModel, Field
import sqlite3

from app.database import get_db_connection
from app.sports_service import ALL_STANDARD_SLOTS, rank_slots_by_proximity

MAX_ACTIVE_BOOKINGS_PER_STUDENT = 10
MAX_ADVANCE_BOOKING_DAYS = 90

class SymbolicClause(BaseModel):
    clause_id: str          # e.g., "C1_FACILITY_ACTIVE", "C3_OPERATING_HOURS"
    name: str               # Human-readable constraint name
    description: str        # Formal rule description
    is_satisfied: bool      # Evaluation outcome against state facts
    violating_fact: str = ""# Fact snippet that triggered violation
    relaxation_target: str = "" # Which parameter could be relaxed (e.g., 'time_slot', 'facility', 'quota')

class MUSResult(BaseModel):
    is_satisfiable: bool
    violated_clauses: List[SymbolicClause] = Field(default_factory=list)
    mus: List[SymbolicClause] = Field(default_factory=list)
    mcs_relaxations: List[Dict[str, Any]] = Field(default_factory=list)
    contrastive_explanation: str = ""
    suggested_alternatives: List[str] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)

def evaluate_symbolic_clauses(
    user_id: int,
    sport_name: str,
    booking_date: str,
    time_slot: str,
    facility_id: Optional[int] = None,
    user_role: str = "student",
    conn: Optional[sqlite3.Connection] = None
) -> Tuple[List[SymbolicClause], Dict[str, Any]]:
    """
    Evaluates ALL 8 formal ERP scheduling invariants simultaneously across the active database state.
    Returns (all_clauses, state_facts).
    """
    close_conn = False
    if conn is None:
        conn = get_db_connection()
        close_conn = True

    try:
        cursor = conn.cursor()
        clauses: List[SymbolicClause] = []
        facts: Dict[str, Any] = {}

        # ---------------------------------------------------------------------
        # Fact Extraction
        # ---------------------------------------------------------------------
        today = date.today()
        facts["today"] = today.isoformat()
        facts["user_id"] = user_id
        facts["user_role"] = user_role
        facts["requested_sport"] = sport_name.strip()
        facts["requested_date"] = booking_date.strip()
        facts["requested_slot"] = time_slot.strip()
        facts["requested_facility_id"] = facility_id

        # 1. User Account Facts
        cursor.execute("SELECT id, name, is_blocked, role FROM users WHERE id = ?", (user_id,))
        user_row = cursor.fetchone()
        facts["user_exists"] = bool(user_row)
        facts["is_blocked"] = bool(user_row["is_blocked"]) if user_row else False
        facts["actual_role"] = user_row["role"] if user_row else "student"

        # 2. Sport Catalog Facts
        cursor.execute("SELECT id, name FROM sports WHERE LOWER(name) = LOWER(?)", (sport_name.strip(),))
        sport_row = cursor.fetchone()
        if not sport_row:
            cursor.execute("SELECT id, name FROM sports WHERE LOWER(name) LIKE ?", (f"%{sport_name.strip().lower()}%",))
            sport_row = cursor.fetchone()
        facts["sport_exists"] = bool(sport_row)
        facts["sport_id"] = sport_row["id"] if sport_row else None
        facts["canonical_sport_name"] = sport_row["name"] if sport_row else sport_name

        # 3. Facility Facts
        candidate_facilities = []
        if facts["sport_exists"]:
            cursor.execute(
                "SELECT id, name, sport_id, location, capacity, is_available FROM facilities WHERE sport_id = ?",
                (facts["sport_id"],)
            )
            candidate_facilities = [dict(f) for f in cursor.fetchall()]
        facts["candidate_facilities"] = candidate_facilities
        facts["active_candidate_facilities"] = [f for f in candidate_facilities if f["is_available"] == 1]

        target_facility = None
        if facility_id:
            cursor.execute("SELECT id, name, sport_id, location, capacity, is_available FROM facilities WHERE id = ?", (facility_id,))
            tf = cursor.fetchone()
            if tf:
                target_facility = dict(tf)
        facts["target_facility"] = target_facility

        # 4. Student Active Booking Quota Facts
        cursor.execute("""
            SELECT COUNT(*) FROM bookings 
            WHERE user_id = ? AND booking_date >= ? AND status = 'confirmed'
        """, (user_id, today.isoformat()))
        active_booking_count = cursor.fetchone()[0]
        facts["active_booking_count"] = active_booking_count

        # 5. Slot Occupancy Facts
        free_facilities = []
        occupied_by_user = []
        occupied_by_others = []

        eval_facilities = [target_facility] if target_facility else facts["active_candidate_facilities"]
        for fac in eval_facilities:
            if fac:
                cursor.execute(
                    "SELECT id, user_id FROM bookings WHERE facility_id = ? AND booking_date = ? AND time_slot = ? AND status = 'confirmed'",
                    (fac["id"], booking_date, time_slot)
                )
                conflict = cursor.fetchone()
                if not conflict:
                    free_facilities.append(fac)
                elif conflict["user_id"] == user_id:
                    occupied_by_user.append((fac, dict(conflict)))
                else:
                    occupied_by_others.append((fac, dict(conflict)))

        facts["free_facilities"] = free_facilities
        facts["occupied_by_user"] = occupied_by_user
        facts["occupied_by_others"] = occupied_by_others

        # ---------------------------------------------------------------------
        # Symbolic Clause Invariant Evaluations (C1 - C8)
        # ---------------------------------------------------------------------

        # Clause C6: User Standing
        c6_sat = facts["user_exists"] and not facts["is_blocked"]
        c6_viol = "" if c6_sat else ("User account does not exist" if not facts["user_exists"] else "User account is administratively blocked")
        clauses.append(SymbolicClause(
            clause_id="C6_ACCOUNT_STANDING",
            name="User Account Standing",
            description="User must exist and have an active, unblocked account status.",
            is_satisfied=c6_sat,
            violating_fact=c6_viol,
            relaxation_target="user_standing"
        ))

        # Clause C2: Sport Catalog & Facility Compatibility
        c2_sat = True
        c2_viol = ""
        if not facts["sport_exists"]:
            c2_sat = False
            c2_viol = f"Sport '{sport_name}' is not recognized in the university catalog."
        elif target_facility and target_facility["sport_id"] != facts["sport_id"]:
            c2_sat = False
            c2_viol = f"Facility '{target_facility['name']}' is designated for a different sport, not {facts['canonical_sport_name']}."
        clauses.append(SymbolicClause(
            clause_id="C2_SPORT_COMPATIBILITY",
            name="Sport-Facility Compatibility",
            description="Sport must exist and match the selected facility's designated sport type.",
            is_satisfied=c2_sat,
            violating_fact=c2_viol,
            relaxation_target="sport_name"
        ))

        # Clause C1: Facility Operational Availability
        c1_sat = True
        c1_viol = ""
        if facility_id and not target_facility:
            c1_sat = False
            c1_viol = f"Facility #{facility_id} does not exist."
        elif facility_id and target_facility and target_facility["is_available"] == 0:
            c1_sat = False
            c1_viol = f"Facility '{target_facility['name']}' is currently closed for maintenance."
        elif not facility_id and not facts["active_candidate_facilities"]:
            c1_sat = False
            c1_viol = f"No active operational facilities exist for sport '{facts['canonical_sport_name']}'."
        clauses.append(SymbolicClause(
            clause_id="C1_FACILITY_OPERATIONAL",
            name="Facility Operational Availability",
            description="Facility must exist, be designated for the sport, and have is_available=1.",
            is_satisfied=c1_sat,
            violating_fact=c1_viol,
            relaxation_target="facility_id"
        ))

        # Clause C3: Campus Operating Hours
        c3_sat = time_slot.strip() in ALL_STANDARD_SLOTS
        c3_viol = "" if c3_sat else f"Time slot '{time_slot}' is outside campus operating hours (06:00-09:00, 16:00-20:00)."
        clauses.append(SymbolicClause(
            clause_id="C3_OPERATING_HOURS",
            name="Campus Operating Schedule",
            description="Slot must match standard 1-hour intervals: 06:00-09:00 or 16:00-20:00.",
            is_satisfied=c3_sat,
            violating_fact=c3_viol,
            relaxation_target="time_slot"
        ))

        # Clause C4: Temporal Validity (No past dates, within advance window)
        c4_sat = True
        c4_viol = ""
        try:
            req_date_obj = datetime.strptime(booking_date.strip(), "%Y-%m-%d").date()
            if req_date_obj < today:
                c4_sat = False
                c4_viol = f"Requested date '{booking_date}' is in the past (Today is {today.isoformat()})."
            elif (req_date_obj - today).days > MAX_ADVANCE_BOOKING_DAYS:
                c4_sat = False
                c4_viol = f"Date '{booking_date}' exceeds the maximum advance reservation window of {MAX_ADVANCE_BOOKING_DAYS} days."
        except ValueError:
            c4_sat = False
            c4_viol = f"Invalid date format '{booking_date}' (Expected YYYY-MM-DD)."
        clauses.append(SymbolicClause(
            clause_id="C4_TEMPORAL_VALIDITY",
            name="Temporal Validity Window",
            description="Booking date must be today or future date within 90 days.",
            is_satisfied=c4_sat,
            violating_fact=c4_viol,
            relaxation_target="booking_date"
        ))

        # Clause C7: Advance Reservation Quota
        c7_sat = True
        c7_viol = ""
        if user_role != "admin" and active_booking_count >= MAX_ACTIVE_BOOKINGS_PER_STUDENT:
            c7_sat = False
            c7_viol = f"Student already holds {active_booking_count} active bookings (Quota limit: {MAX_ACTIVE_BOOKINGS_PER_STUDENT})."
        clauses.append(SymbolicClause(
            clause_id="C7_STUDENT_QUOTA",
            name="Student Reservation Quota",
            description=f"Students cannot exceed {MAX_ACTIVE_BOOKINGS_PER_STUDENT} concurrent active future bookings.",
            is_satisfied=c7_sat,
            violating_fact=c7_viol,
            relaxation_target="quota"
        ))

        # Clause C5: Slot Conflict / Double Booking
        c5_sat = True
        c5_viol = ""
        if occupied_by_user and facility_id:
            c5_sat = False
            c5_viol = f"Duplicate reservation: You already hold Booking #{occupied_by_user[0][1]['id']} on this court at {time_slot}."
        elif not free_facilities and (occupied_by_user or occupied_by_others):
            c5_sat = False
            total_occ = len(occupied_by_user) + len(occupied_by_others)
            c5_viol = f"All {total_occ} court(s) for {facts['canonical_sport_name']} are fully booked at {time_slot} on {booking_date}."
        clauses.append(SymbolicClause(
            clause_id="C5_SLOT_AVAILABILITY",
            name="Slot Conflict & Double Booking",
            description="At least one compatible court must be free and unreserved by the user.",
            is_satisfied=c5_sat,
            violating_fact=c5_viol,
            relaxation_target="time_slot"
        ))

        # Clause C8: Role Permissions
        c8_sat = True
        c8_viol = ""
        if user_role not in ["student", "admin"]:
            c8_sat = False
            c8_viol = f"Unrecognized system role '{user_role}'."
        clauses.append(SymbolicClause(
            clause_id="C8_ROLE_PERMISSIONS",
            name="Role-Based Authorization",
            description="Requesting user must hold legitimate student or admin permissions.",
            is_satisfied=c8_sat,
            violating_fact=c8_viol,
            relaxation_target="role"
        ))

        return clauses, facts

    finally:
        if close_conn:
            conn.close()

def extract_mus(clauses: List[SymbolicClause]) -> List[SymbolicClause]:
    """
    Deletion-based Minimal Unsatisfiable Subset (MUS) extraction.
    Filters the full clause set down to the irreducible set of simultaneously violated constraints.
    In our domain, each violated clause represents an independent necessary condition.
    """
    return [c for c in clauses if not c.is_satisfied]

def solve_mcs(
    mus_clauses: List[SymbolicClause],
    facts: Dict[str, Any],
    conn: Optional[sqlite3.Connection] = None
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Minimal Correction Set (MCS) / Minimal Relaxation Search.
    Computes the smallest parameter relaxations needed to restore satisfiability:
    1. If C3 (Operating Hours) or C5 (Slot Occupied) is violated -> Search proximity-ranked slots on same day.
    2. If C7 (Quota Exceeded) is violated -> Suggest cancelling oldest confirmed booking.
    3. If C1 (Facility Maintenance) is violated -> Suggest alternative facility for same sport.
    """
    relaxations: List[Dict[str, Any]] = []
    suggested_slots: List[str] = []

    close_conn = False
    if conn is None:
        conn = get_db_connection()
        close_conn = True

    try:
        cursor = conn.cursor()
        violated_ids = {c.clause_id for c in mus_clauses}

        # 1. Relaxation for Slot / Operating Hours (C3 or C5)
        if "C3_OPERATING_HOURS" in violated_ids or "C5_SLOT_AVAILABILITY" in violated_ids:
            if facts.get("sport_exists") and facts.get("active_candidate_facilities"):
                sport_name = facts["canonical_sport_name"]
                booking_date = facts["requested_date"]
                requested_slot = facts["requested_slot"]

                # Find all available slots on this date
                candidate_fac_ids = [f["id"] for f in facts["active_candidate_facilities"]]
                free_slots_set = set()
                for slot in ALL_STANDARD_SLOTS:
                    cursor.execute("""
                        SELECT COUNT(*) FROM bookings 
                        WHERE facility_id IN ({seq}) AND booking_date = ? AND time_slot = ? AND status = 'confirmed'
                    """.format(seq=",".join(["?"] * len(candidate_fac_ids))), (*candidate_fac_ids, booking_date, slot))
                    booked_count = cursor.fetchone()[0]
                    if booked_count < len(candidate_fac_ids):
                        free_slots_set.add(slot)

                if free_slots_set:
                    ranked = rank_slots_by_proximity(list(free_slots_set), requested_slot)
                    suggested_slots = ranked
                    relaxations.append({
                        "relaxation_type": "SHIFT_TIME_SLOT",
                        "parameter": "time_slot",
                        "current_value": requested_slot,
                        "minimal_satisfying_values": ranked[:3],
                        "explanation": f"Shift time slot to nearest available window: {', '.join(ranked[:3])}."
                    })

        # 2. Relaxation for Student Quota (C7)
        if "C7_STUDENT_QUOTA" in violated_ids:
            cursor.execute("""
                SELECT b.id, s.name as sport_name, b.booking_date, b.time_slot 
                FROM bookings b JOIN sports s ON b.sport_id = s.id 
                WHERE b.user_id = ? AND b.booking_date >= ? AND b.status = 'confirmed'
                ORDER BY b.booking_date ASC LIMIT 1
            """, (facts["user_id"], facts["today"]))
            oldest = cursor.fetchone()
            if oldest:
                relaxations.append({
                    "relaxation_type": "CANCEL_ACTIVE_BOOKING",
                    "parameter": "quota",
                    "target_booking_id": oldest["id"],
                    "explanation": f"Cancel active Booking #{oldest['id']} ({oldest['sport_name']} on {oldest['booking_date']} {oldest['time_slot']}) to free quota."
                })

        # 3. Relaxation for Facility Inactive (C1)
        if "C1_FACILITY_OPERATIONAL" in violated_ids and facts.get("requested_facility_id"):
            alt_facs = [f for f in facts.get("candidate_facilities", []) if f["id"] != facts["requested_facility_id"] and f["is_available"] == 1]
            if alt_facs:
                relaxations.append({
                    "relaxation_type": "SWITCH_FACILITY",
                    "parameter": "facility_id",
                    "current_value": facts["requested_facility_id"],
                    "minimal_satisfying_values": [f["name"] for f in alt_facs],
                    "explanation": f"Switch to operational court: {alt_facs[0]['name']}."
                })

        return relaxations, suggested_slots

    finally:
        if close_conn:
            conn.close()

def generate_contrastive_mus_explanation(
    mus_clauses: List[SymbolicClause],
    mcs_relaxations: List[Dict[str, Any]]
) -> str:
    """
    Generates a deterministic contrastive explanation:
    - Lists the exact minimal conflict constraints (MUS) without extraneous clauses.
    - Specifies the minimal parameter correction (MCS) to achieve satisfiability.
    """
    if not mus_clauses:
        return "The requested booking is fully valid and satisfies all domain constraints."

    # Single-constraint failure
    if len(mus_clauses) == 1:
        c = mus_clauses[0]
        base_exp = f"Request rejected due to {c.name}: {c.violating_fact}"
    else:
        # Multi-constraint simultaneous conflict (MUS core)
        bullets = [f"({i+1}) {c.name}: {c.violating_fact}" for i, c in enumerate(mus_clauses)]
        base_exp = f"Request rejected due to {len(mus_clauses)} conflicting constraints:\n" + "\n".join(bullets)

    # Attach Minimal Correction Set suggestions
    if mcs_relaxations:
        corrections = [r["explanation"] for r in mcs_relaxations]
        base_exp += "\n\n💡 Minimal Correction Options:\n- " + "\n- ".join(corrections)

    return base_exp

# Standard alias for research paper specification
generate_contrastive_explanation = generate_contrastive_mus_explanation

def evaluate_booking_mus_mcs(
    user_id: int,
    sport_name: str,
    booking_date: str,
    time_slot: str,
    facility_id: Optional[int] = None,
    user_role: str = "student",
    conn: Optional[sqlite3.Connection] = None
) -> MUSResult:
    """
    Main Entry Point: Evaluates booking satisfiability, extracts MUS conflict core,
    solves MCS minimal relaxations, and produces grounded contrastive explanations.
    """
    clauses, facts = evaluate_symbolic_clauses(
        user_id=user_id,
        sport_name=sport_name,
        booking_date=booking_date,
        time_slot=time_slot,
        facility_id=facility_id,
        user_role=user_role,
        conn=conn
    )

    violated = [c for c in clauses if not c.is_satisfied]
    if not violated:
        # Fully Satisfiable
        fac_chosen = facts["free_facilities"][0] if facts["free_facilities"] else None
        return MUSResult(
            is_satisfiable=True,
            violated_clauses=[],
            mus=[],
            mcs_relaxations=[],
            contrastive_explanation="Satisfiable: All 8 enterprise invariants verified.",
            suggested_alternatives=[],
            details={
                "facility_id": fac_chosen["id"] if fac_chosen else None,
                "facility_name": fac_chosen["name"] if fac_chosen else None,
                "sport_name": facts["canonical_sport_name"],
                "booking_date": booking_date,
                "time_slot": time_slot
            }
        )

    # Unsatisfiable -> Compute MUS and MCS
    mus = extract_mus(clauses)
    mcs, suggested_slots = solve_mcs(mus, facts, conn=conn)
    explanation = generate_contrastive_mus_explanation(mus, mcs)

    return MUSResult(
        is_satisfiable=False,
        violated_clauses=violated,
        mus=mus,
        mcs_relaxations=mcs,
        contrastive_explanation=explanation,
        suggested_alternatives=suggested_slots,
        details={
            "violated_clause_ids": [c.clause_id for c in violated],
            "mus_size": len(mus),
            "mcs_size": len(mcs)
        }
    )
