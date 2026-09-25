"""
tests/test_tournament_solver.py
--------------------------------
Unit and Invariant Verification Tests for Z3 SMT Tournament Scheduling Engine.
"""

import pytest
from app.tournament_solver import (
    TournamentRequest,
    TournamentSolverResult,
    solve_tournament_schedule,
    get_slot_start_hour
)

def test_feasible_4_team_round_robin_tournament():
    """Verify that a 4-team round-robin tournament is scheduled feasibly across 2 courts over 2 days."""
    req = TournamentRequest(
        sport_name="Badminton",
        team_names=["Team Alpha", "Team Beta", "Team Gamma", "Team Delta"],
        court_names=["Badminton Court 1", "Badminton Court 2"],
        dates=["2026-10-01", "2026-10-02"],
        daily_slots=["06:00 - 07:00", "07:00 - 08:00", "16:00 - 17:00", "17:00 - 18:00"],
        min_rest_hours=2,
        tournament_type="round_robin",
        check_db_conflicts=False
    )
    res = solve_tournament_schedule(req)
    assert res.is_feasible is True
    assert res.total_matches == 6  # 4C2 = 6 matches
    assert len(res.schedule) == 6
    assert res.solving_time_ms > 0

    # Invariant 1: Court Non-Overlap
    venue_slots = [(m.date, m.time_slot, m.court_name) for m in res.schedule]
    assert len(venue_slots) == len(set(venue_slots)), "Duplicate court allocation detected!"

    # Invariant 2: Team Concurrency
    for m1 in res.schedule:
        for m2 in res.schedule:
            if m1.match_id != m2.match_id and m1.date == m2.date and m1.time_slot == m2.time_slot:
                teams1 = {m1.team_a, m1.team_b}
                teams2 = {m2.team_a, m2.team_b}
                assert len(teams1 & teams2) == 0, f"Team concurrency violation: {teams1 & teams2} playing simultaneously!"

def test_insufficient_capacity_tournament():
    """Verify that an impossible tournament request (6 matches into 2 slots) fails with clear capacity explanation."""
    req = TournamentRequest(
        sport_name="Tennis",
        team_names=["Team A", "Team B", "Team C", "Team D"],
        court_names=["Tennis Court 1"],
        dates=["2026-10-01"],
        daily_slots=["06:00 - 07:00", "07:00 - 08:00"],  # Only 2 available match slots
        min_rest_hours=0,
        tournament_type="round_robin",
        check_db_conflicts=False
    )
    res = solve_tournament_schedule(req)
    assert res.is_feasible is False
    assert "Insufficient court capacity" in res.infeasibility_reason

def test_rest_interval_constraint_enforcement():
    """Verify that teams are not scheduled into consecutive slots when min_rest_hours=2."""
    req = TournamentRequest(
        sport_name="Squash",
        team_names=["Squash A", "Squash B", "Squash C"],
        court_names=["Squash Court 1", "Squash Court 2"],
        dates=["2026-10-01"],
        daily_slots=["06:00 - 07:00", "08:00 - 09:00", "16:00 - 17:00", "18:00 - 19:00"],
        min_rest_hours=2,
        tournament_type="round_robin",
        check_db_conflicts=False
    )
    res = solve_tournament_schedule(req)
    assert res.is_feasible is True
    assert res.total_matches == 3

    # Verify rest hours for any team playing twice on the same day
    for team in req.team_names:
        team_matches = [m for m in res.schedule if team in (m.team_a, m.team_b)]
        if len(team_matches) > 1:
            for i in range(len(team_matches)):
                for j in range(i + 1, len(team_matches)):
                    h1 = get_slot_start_hour(team_matches[i].time_slot)
                    h2 = get_slot_start_hour(team_matches[j].time_slot)
                    assert abs(h1 - h2) >= 2, f"Rest violation for {team}: played at {h1}:00 and {h2}:00"

def test_single_elimination_mode():
    """Verify single elimination tournament mode scheduling across complete bracket."""
    # 4 teams -> 3 matches (2 semifinals + 1 final)
    req4 = TournamentRequest(
        sport_name="Cricket",
        team_names=["Team 1", "Team 2", "Team 3", "Team 4"],
        court_names=["Main Ground"],
        dates=["2026-10-01", "2026-10-02"],
        daily_slots=["06:00 - 07:00", "08:00 - 09:00", "16:00 - 17:00", "18:00 - 19:00"],
        tournament_type="single_elimination",
        check_db_conflicts=False
    )
    res4 = solve_tournament_schedule(req4)
    assert res4.is_feasible is True
    assert res4.total_matches == 3  # 4 - 1 = 3 matches

    # 8 teams -> 7 matches (4 quarterfinals + 2 semifinals + 1 final)
    req8 = TournamentRequest(
        sport_name="Badminton",
        team_names=[f"Team {i}" for i in range(1, 9)],
        court_names=["Badminton Court 1", "Badminton Court 2"],
        dates=["2026-10-01", "2026-10-02"],
        daily_slots=["06:00 - 07:00", "07:00 - 08:00", "08:00 - 09:00", "16:00 - 17:00", "17:00 - 18:00", "18:00 - 19:00", "19:00 - 20:00"],
        min_rest_hours=1,
        tournament_type="single_elimination",
        check_db_conflicts=False
    )
    res8 = solve_tournament_schedule(req8)
    assert res8.is_feasible is True
    assert res8.total_matches == 7  # 8 - 1 = 7 matches
    assert len(res8.schedule) == 7

def test_20_teams_1_court_1_day_infeasible_exact_parameters():
    """Verify Bug 2 requirement: 20 teams on 1 court in 1 day with 4h rest must return 190 matches and is_feasible=False."""
    teams_20 = [f"Team {i}" for i in range(1, 21)]
    req = TournamentRequest(
        sport_name="Badminton",
        team_names=teams_20,
        court_names=["Badminton Court 1"],
        dates=["2026-10-01"],
        daily_slots=["06:00 - 07:00", "07:00 - 08:00", "08:00 - 09:00", "16:00 - 17:00", "17:00 - 18:00", "18:00 - 19:00", "19:00 - 20:00"],
        min_rest_hours=4,
        tournament_type="round_robin",
        check_db_conflicts=False
    )
    res = solve_tournament_schedule(req)
    assert res.is_feasible is False
    assert res.total_matches == 190  # 20 * 19 / 2 = 190
    assert "Insufficient court capacity" in res.infeasibility_reason
    assert "190 matches" in res.infeasibility_reason
    assert "7 court-slot units" in res.infeasibility_reason
    assert res.unsat_core == ["CAPACITY_EXCEEDED"]

def test_8_teams_2_courts_2_days_scheduling():
    """Verify scheduling 8 teams on 2 courts over 2 days."""
    teams_8 = [f"Team {i}" for i in range(1, 9)]
    req = TournamentRequest(
        sport_name="Badminton",
        team_names=teams_8,
        court_names=["Badminton Court 1", "Badminton Court 2"],
        dates=["2026-10-01", "2026-10-02"],
        daily_slots=["06:00 - 07:00", "07:00 - 08:00", "08:00 - 09:00", "16:00 - 17:00", "17:00 - 18:00", "18:00 - 19:00", "19:00 - 20:00"],
        min_rest_hours=2,
        tournament_type="round_robin",
        check_db_conflicts=False
    )
    res = solve_tournament_schedule(req)
    assert res.total_matches == 28  # 8C2 = 28
    # 28 matches in 28 available slots
    assert res.solving_time_ms > 0

