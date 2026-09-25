# [SYNTHETIC DATASET — RESEARCH EXPERIMENTATION ONLY]
"""
app/demand_dataset.py
----------------------
Synthetic Athletic Facility Booking & Congestion Dataset Generator.

Research Integrity Statement:
This dataset is SYNTHETICALLY generated using empirical domain heuristics
(diurnal peaks, academic exam schedules, weekend recreational shifts, and sport popularity distributions)
to enable reproducible machine-learning demand forecasting experiments.
"""

import os
import math
import random
import pandas as pd
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional

SPORTS_PROBABILITY_WEIGHTS = {
    "Badminton": 0.35,
    "Football": 0.20,
    "Cricket": 0.15,
    "Basketball": 0.10,
    "Table Tennis": 0.08,
    "Squash": 0.05,
    "Tennis": 0.04,
    "Swimming": 0.03
}

def generate_synthetic_demand_dataset(
    start_date: str = "2025-01-01",
    days: int = 365,
    seed: int = 42,
    output_csv_path: Optional[str] = None
) -> pd.DataFrame:
    """
    Generates a 365-day hourly dataset of synthetic sports facility utilization.
    """
    random.seed(seed)
    records = []
    
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    operating_hours = [6, 7, 8, 16, 17, 18, 19]  # Operating windows: 06-09 and 16-20

    for day_offset in range(days):
        current_date = start_dt + timedelta(days=day_offset)
        iso_date = current_date.isoformat()
        day_of_week = current_date.weekday()  # 0=Mon, 6=Sun
        is_weekend = int(day_of_week in [5, 6])
        
        # Exam season simulation (May and December)
        is_exam_period = int(current_date.month in [5, 12] and current_date.day > 10)
        
        # Seasonal weather factor (lower outdoor demand in extreme heat/monsoon: June/July)
        is_monsoon = int(current_date.month in [6, 7])

        for hour in operating_hours:
            slot_str = f"{hour:02d}:00 - {(hour+1):02d}:00"
            
            # Base diurnal curve: evening peak (17-19) highest, morning peak (06-08) secondary
            if hour in [17, 18, 19]:
                base_hour_factor = 0.85
            elif hour in [7, 8]:
                base_hour_factor = 0.70
            elif hour == 16:
                base_hour_factor = 0.65
            else:  # hour == 6
                base_hour_factor = 0.50

            # Weekend modifier: evening rush starts earlier, morning rush lighter
            if is_weekend:
                if hour in [16, 17, 18]:
                    base_hour_factor += 0.10
                elif hour == 6:
                    base_hour_factor -= 0.15

            # Exam modifier: reduction in recreation
            if is_exam_period:
                base_hour_factor *= 0.60

            for sport_name, sport_weight in SPORTS_PROBABILITY_WEIGHTS.items():
                is_outdoor = sport_name in ["Football", "Cricket", "Tennis"]
                weather_penalty = 0.25 if (is_outdoor and is_monsoon) else 0.0

                # Calculate occupancy probability
                target_occupancy = (base_hour_factor * 0.70 + sport_weight * 0.30) - weather_penalty
                noise = random.gauss(0, 0.05)
                occupancy_rate = max(0.05, min(0.98, target_occupancy + noise))

                # Synthesize booking count based on a 4-court facility assumption
                max_capacity = 4
                booking_count = min(max_capacity, max(0, round(occupancy_rate * max_capacity)))
                actual_occupancy_pct = round((booking_count / max_capacity) * 100, 1)

                records.append({
                    "date": iso_date,
                    "hour": hour,
                    "time_slot": slot_str,
                    "day_of_week": day_of_week,
                    "is_weekend": is_weekend,
                    "is_exam_period": is_exam_period,
                    "sport_name": sport_name,
                    "is_outdoor": int(is_outdoor),
                    "booking_count": booking_count,
                    "occupancy_rate": round(occupancy_rate, 4),
                    "occupancy_pct": actual_occupancy_pct,
                    "congestion_level": "Peak" if actual_occupancy_pct >= 75.0 else ("Moderate" if actual_occupancy_pct >= 50.0 else "Low")
                })

    df = pd.DataFrame(records)
    
    if output_csv_path:
        os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)
        df.to_csv(output_csv_path, index=False)
        print(f"[+] Exported {len(df)} synthetic demand records to {output_csv_path}")

    return df

if __name__ == "__main__":
    df = generate_synthetic_demand_dataset(output_csv_path="data/synthetic_demand_dataset.csv")
    print("Generated synthetic dataset sample:")
    print(df.head())
