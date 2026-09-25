"""
tests/benchmark_tournament.py
------------------------------
Reproducible Empirical Benchmark for Z3 SMT Tournament Scheduling.
Evaluates solving latency, scale, and constraint satisfaction across 3 problem sizes.
"""

import os
import sys
import json
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.tournament_solver import TournamentRequest, solve_tournament_schedule

def run_tournament_benchmark():
    print("=" * 70)
    print("[*] RUNNING Z3 SMT TOURNAMENT SCHEDULING BENCHMARK")
    print("=" * 70)

    scenarios = [
        {
            "name": "Small (4 Teams, 2 Courts, 1 Day)",
            "teams": ["Alpha", "Beta", "Gamma", "Delta"],
            "courts": ["Court 1", "Court 2"],
            "dates": ["2026-10-01"],
            "slots": ["06:00 - 07:00", "07:00 - 08:00", "08:00 - 09:00", "16:00 - 17:00", "17:00 - 18:00", "18:00 - 19:00", "19:00 - 20:00"],
            "min_rest": 2
        },
        {
            "name": "Medium (6 Teams, 3 Courts, 2 Days)",
            "teams": [f"Team_{i}" for i in range(1, 7)],
            "courts": [f"Court_{i}" for i in range(1, 4)],
            "dates": ["2026-10-01", "2026-10-02"],
            "slots": ["06:00 - 07:00", "07:00 - 08:00", "08:00 - 09:00", "16:00 - 17:00", "17:00 - 18:00", "18:00 - 19:00", "19:00 - 20:00"],
            "min_rest": 2
        },
        {
            "name": "Large (8 Teams, 4 Courts, 3 Days)",
            "teams": [f"Team_{i}" for i in range(1, 9)],
            "courts": [f"Court_{i}" for i in range(1, 5)],
            "dates": ["2026-10-01", "2026-10-02", "2026-10-03"],
            "slots": ["06:00 - 07:00", "07:00 - 08:00", "08:00 - 09:00", "16:00 - 17:00", "17:00 - 18:00", "18:00 - 19:00", "19:00 - 20:00"],
            "min_rest": 2
        }
    ]

    results = []
    for sc in scenarios:
        req = TournamentRequest(
            sport_name="Badminton",
            team_names=sc["teams"],
            court_names=sc["courts"],
            dates=sc["dates"],
            daily_slots=sc["slots"],
            min_rest_hours=sc["min_rest"],
            check_db_conflicts=False
        )
        res = solve_tournament_schedule(req)
        print(f"[+] Scenario: {sc['name']}")
        print(f"    - Feasible: {res.is_feasible}")
        print(f"    - Matches: {res.total_matches}")
        print(f"    - Solving Time: {res.solving_time_ms} ms")
        
        results.append({
            "scenario": sc["name"],
            "team_count": len(sc["teams"]),
            "court_count": len(sc["courts"]),
            "date_count": len(sc["dates"]),
            "total_matches": res.total_matches,
            "is_feasible": res.is_feasible,
            "solving_time_ms": res.solving_time_ms
        })

    with open("tournament_benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n[+] Saved tournament benchmark to tournament_benchmark_results.json")

if __name__ == "__main__":
    run_tournament_benchmark()
