"""
app/tournament_solver.py
-------------------------
SMT/CP Combinatorial Tournament Scheduling Engine using Microsoft Z3 Solver.

Formal Model:
Given a set of teams T = {t_1, ..., t_N}, courts C = {c_1, ..., c_K},
dates D = {d_1, ..., d_P}, and daily operating slots S = {s_1, ..., s_Q}:
A match set M is mapped to decision tuples (d_m, s_m, c_m) subject to:
1. Court Exclusivity: For m1 != m2, not (d_m1 == d_m2 and s_m1 == s_m2 and c_m1 == c_m2)
2. Team Exclusivity: If T(m1) intersect T(m2) != empty, not (d_m1 == d_m2 and s_m1 == s_m2)
3. Minimum Rest Interval: If T(m1) intersect T(m2) != empty and d_m1 == d_m2, |hour(s_m1) - hour(s_m2)| >= min_rest_hours
4. Operating Schedule: Slots restricted to valid campus operating intervals
5. Facility Availability: Respects existing confirmed reservations in the database.
"""

import time
import re
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, date, timedelta
from pydantic import BaseModel, Field
import z3

from app.database import get_db_connection
from app.sports_service import ALL_STANDARD_SLOTS

class TournamentRequest(BaseModel):
    sport_name: str
    team_names: List[str] = Field(min_length=2)
    court_names: Optional[List[str]] = None
    dates: List[str] = Field(min_length=1)
    daily_slots: Optional[List[str]] = None
    min_rest_hours: int = 2
    tournament_type: str = "round_robin"  # "round_robin" or "single_elimination"
    check_db_conflicts: bool = True

class MatchSchedule(BaseModel):
    match_id: int
    team_a: str
    team_b: str
    sport_name: str
    date: str
    time_slot: str
    court_name: str
    round_number: int = 1

class TournamentSolverResult(BaseModel):
    is_feasible: bool
    total_matches: int
    schedule: List[MatchSchedule] = Field(default_factory=list)
    infeasibility_reason: Optional[str] = None
    unsat_core: List[str] = Field(default_factory=list)
    solving_time_ms: float = 0.0
    summary: str = ""
    solver_engine: str = "Microsoft Z3 SMT Solver"
    metadata: Dict[str, Any] = Field(default_factory=dict)

def get_slot_start_hour(slot_str: str) -> int:
    m = re.search(r"(\d{1,2}):\d{2}", slot_str)
    return int(m.group(1)) if m else 6

def generate_tournament_matches(teams: List[str], tournament_type: str) -> List[Dict[str, Any]]:
    """
    Generates match definitions for either Round Robin or Single Elimination tournament.
    """
    matches = []
    match_id = 1

    if tournament_type == "single_elimination":
        # Hierarchical bracket generation (Quarterfinals -> Semifinals -> Final)
        current_competitors = [(t, None) for t in teams]
        round_num = 1
        
        while len(current_competitors) > 1:
            next_competitors = []
            num_matches = len(current_competitors) // 2
            
            if num_matches == 1:
                r_name = "Final"
            elif num_matches == 2:
                r_name = "Semifinals"
            elif num_matches == 4:
                r_name = "Quarterfinals"
            else:
                r_name = f"Round {round_num}"

            for i in range(0, len(current_competitors) - 1, 2):
                t_a, m_a = current_competitors[i]
                t_b, m_b = current_competitors[i+1]
                deps = [m for m in (m_a, m_b) if m is not None]
                
                matches.append({
                    "match_id": match_id,
                    "team_a": t_a,
                    "team_b": t_b,
                    "round_number": round_num,
                    "round_name": r_name,
                    "depends_on": deps
                })
                next_competitors.append((f"Winner M{match_id}", match_id))
                match_id += 1

            current_competitors = next_competitors
            round_num += 1

    else:  # Round Robin: every team plays every other team once
        for i in range(len(teams)):
            for j in range(i + 1, len(teams)):
                matches.append({
                    "match_id": match_id,
                    "team_a": teams[i],
                    "team_b": teams[j],
                    "round_number": 1,
                    "round_name": "Round Robin",
                    "depends_on": []
                })
                match_id += 1

    return matches

def solve_tournament_schedule(req: TournamentRequest) -> TournamentSolverResult:
    start_time = time.perf_counter()
    teams = [t.strip() for t in req.team_names if t.strip()]
    if len(teams) < 2:
        return TournamentSolverResult(
            is_feasible=False,
            total_matches=0,
            infeasibility_reason="At least 2 teams are required to schedule a tournament."
        )

    courts = req.court_names
    if not courts or len(courts) == 0:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT f.name FROM facilities f
                JOIN sports s ON f.sport_id = s.id
                WHERE LOWER(s.name) = LOWER(?)
            """, (req.sport_name.strip(),))
            rows = cursor.fetchall()
            courts = [r["name"] for r in rows] if rows else [f"{req.sport_name} Court 1", f"{req.sport_name} Court 2"]
            conn.close()
        except Exception:
            courts = [f"{req.sport_name} Court 1", f"{req.sport_name} Court 2"]

    dates = req.dates
    slots = req.daily_slots or ALL_STANDARD_SLOTS
    slot_hours = [get_slot_start_hour(s) for s in slots]

    match_defs = generate_tournament_matches(teams, req.tournament_type)
    total_matches = len(match_defs)
    total_available_slots = len(dates) * len(slots) * len(courts)

    if total_matches > total_available_slots:
        elapsed = (time.perf_counter() - start_time) * 1000
        if req.tournament_type == "round_robin":
            math_formula = f"n(n-1)/2 = {len(teams)}×{len(teams)-1}/2 = {total_matches} matches"
        else:
            math_formula = f"n-1 = {len(teams)}-1 = {total_matches} matches"
            
        msg = (
            f"Insufficient court capacity: {total_matches} matches required for {len(teams)} teams "
            f"({req.tournament_type}: {math_formula}), but only {total_available_slots} court-slot units available "
            f"across {len(dates)} day(s) on {len(courts)} court(s) ({len(dates)} day(s) × {len(slots)} slots/day × {len(courts)} court(s))."
        )
        return TournamentSolverResult(
            is_feasible=False,
            total_matches=total_matches,
            infeasibility_reason=msg,
            unsat_core=["CAPACITY_EXCEEDED"],
            solving_time_ms=round(elapsed, 3),
            summary=f"❌ Tournament schedule infeasible: {msg} Consider adding more courts or days."
        )

    db_blocked_slots = set()
    if req.check_db_conflicts:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT b.booking_date, b.time_slot, f.name as facility_name
                FROM bookings b
                JOIN facilities f ON b.facility_id = f.id
                WHERE b.status = 'confirmed'
            """)
            for row in cursor.fetchall():
                db_blocked_slots.add((row["booking_date"], row["time_slot"], row["facility_name"]))
            conn.close()
        except Exception:
            pass

    solver = z3.Solver()
    solver.set("timeout", 15000)
    date_vars = [z3.Int(f"m_{i}_date") for i in range(total_matches)]
    slot_vars = [z3.Int(f"m_{i}_slot") for i in range(total_matches)]
    court_vars = [z3.Int(f"m_{i}_court") for i in range(total_matches)]

    for i in range(total_matches):
        solver.add(date_vars[i] >= 0, date_vars[i] < len(dates))
        solver.add(slot_vars[i] >= 0, slot_vars[i] < len(slots))
        solver.add(court_vars[i] >= 0, court_vars[i] < len(courts))

    # Constraint 1: Court Non-Overlap (No two matches on same court at same time)
    for i in range(total_matches):
        for j in range(i + 1, total_matches):
            same_venue = z3.And(date_vars[i] == date_vars[j], slot_vars[i] == slot_vars[j], court_vars[i] == court_vars[j])
            solver.assert_and_track(z3.Not(same_venue), f"court_exclusive_m{i}_m{j}")

    if req.tournament_type == "single_elimination":
        # Constraint 2a: Bracket Round Precedence & Rest Interval
        match_id_to_idx = {m["match_id"]: idx for idx, m in enumerate(match_defs)}
        slot_gap = max(1, req.min_rest_hours)

        for idx, m in enumerate(match_defs):
            for dep_id in m["depends_on"]:
                parent_idx = match_id_to_idx[dep_id]
                same_day_after = z3.And(date_vars[idx] == date_vars[parent_idx], slot_vars[idx] >= slot_vars[parent_idx] + slot_gap)
                next_day = (date_vars[idx] > date_vars[parent_idx])
                solver.assert_and_track(
                    z3.Or(same_day_after, next_day),
                    f"precedence_m{parent_idx}_to_m{idx}"
                )

    else:
        # Constraint 2b: Team Non-Overlap (Round Robin)
        for i in range(total_matches):
            t_i1 = match_defs[i]["team_a"]
            t_i2 = match_defs[i]["team_b"]
            for j in range(i + 1, total_matches):
                t_j1 = match_defs[j]["team_a"]
                t_j2 = match_defs[j]["team_b"]
                if bool({t_i1, t_i2} & {t_j1, t_j2}):
                    same_time = z3.And(date_vars[i] == date_vars[j], slot_vars[i] == slot_vars[j])
                    solver.assert_and_track(z3.Not(same_time), f"team_concurrency_{t_i1}_{t_i2}_vs_{t_j1}_{t_j2}")

        # Constraint 3: Minimum Rest Interval (Round Robin)
        if req.min_rest_hours > 0:
            invalid_slot_pairs = [
                (sa_idx, sb_idx)
                for sa_idx, ha in enumerate(slot_hours)
                for sb_idx, hb in enumerate(slot_hours)
                if abs(ha - hb) < req.min_rest_hours
            ]
            for i in range(total_matches):
                t_i1 = match_defs[i]["team_a"]
                t_i2 = match_defs[i]["team_b"]
                for j in range(i + 1, total_matches):
                    t_j1 = match_defs[j]["team_a"]
                    t_j2 = match_defs[j]["team_b"]
                    if bool({t_i1, t_i2} & {t_j1, t_j2}):
                        conflict_exprs = [z3.And(slot_vars[i] == sa, slot_vars[j] == sb) for sa, sb in invalid_slot_pairs]
                        if conflict_exprs:
                            solver.assert_and_track(
                                z3.Not(z3.And(date_vars[i] == date_vars[j], z3.Or(conflict_exprs))),
                                f"rest_interval_m{i}_m{j}"
                            )

    # Constraint 4: Blocked Slots in DB
    for d_idx, d_val in enumerate(dates):
        for s_idx, s_val in enumerate(slots):
            for c_idx, c_val in enumerate(courts):
                if (d_val, s_val, c_val) in db_blocked_slots:
                    for i in range(total_matches):
                        solver.add(z3.Not(z3.And(date_vars[i] == d_idx, slot_vars[i] == s_idx, court_vars[i] == c_idx)))

    check_res = solver.check()
    elapsed = (time.perf_counter() - start_time) * 1000

    if check_res == z3.sat:
        model = solver.model()
        schedule_list = []
        for i in range(total_matches):
            m_def = match_defs[i]
            d_idx = model[date_vars[i]].as_long()
            s_idx = model[slot_vars[i]].as_long()
            c_idx = model[court_vars[i]].as_long()
            schedule_list.append(MatchSchedule(
                match_id=m_def["match_id"],
                team_a=m_def["team_a"],
                team_b=m_def["team_b"],
                sport_name=req.sport_name,
                date=dates[d_idx],
                time_slot=slots[s_idx],
                court_name=courts[c_idx],
                round_number=m_def["round_number"]
            ))
        schedule_list.sort(key=lambda x: (x.date, x.time_slot, x.court_name))
        
        # Formulate readable summary
        match_lines = [
            f"- **Match {m.match_id} ({m.team_a} vs {m.team_b})**: {m.date} ({m.time_slot}) on {m.court_name}"
            for m in schedule_list[:8]
        ]
        if len(schedule_list) > 8:
            match_lines.append(f"- *... and {len(schedule_list) - 8} more matches scheduled.*")
            
        summary_msg = (
            f"🏆 **{req.sport_name} Tournament Schedule ({req.tournament_type.replace('_', ' ').title()})**:\n"
            f"• **Teams:** {len(teams)} | **Total Matches:** {total_matches} | **Courts:** {len(courts)} | **Duration:** {len(dates)} day(s)\n"
            f"• **Status:** Feasible with 0 constraint violations ({round(elapsed, 2)} ms)\n\n"
            f"**Match Schedule:**\n" + "\n".join(match_lines)
        )

        return TournamentSolverResult(
            is_feasible=True,
            total_matches=total_matches,
            schedule=schedule_list,
            solving_time_ms=round(elapsed, 3),
            summary=summary_msg,
            metadata={
                "teams": teams,
                "courts": courts,
                "dates": dates,
                "min_rest_hours": req.min_rest_hours,
                "tournament_type": req.tournament_type
            }
        )
    else:
        core = [str(c) for c in solver.unsat_core()]
        reason = f"Tournament schedule is mathematically infeasible under given constraints ({total_matches} matches across {len(courts)} court(s) and {len(dates)} day(s) with {req.min_rest_hours}h rest)."
        if any("rest_interval" in c for c in core) or any("precedence" in c for c in core):
            reason += f" The minimum rest interval of {req.min_rest_hours} hours and round precedence cannot be satisfied with the available daily slots."
        elif any("court_exclusive" in c for c in core):
            reason += " Insufficient distinct courts available to prevent concurrent court overlapping."
        elif any("team_concurrency" in c for c in core):
            reason += " Team participation concurrency cannot be satisfied within the provided date/slot bounds."

        return TournamentSolverResult(
            is_feasible=False,
            total_matches=total_matches,
            infeasibility_reason=reason,
            unsat_core=core[:10],
            solving_time_ms=round(elapsed, 3),
            summary="Schedule generation failed: No mathematically valid configuration exists under these constraints.",
            metadata={"teams": teams, "courts": courts, "dates": dates, "min_rest_hours": req.min_rest_hours}
        )
