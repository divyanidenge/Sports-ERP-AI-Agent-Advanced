"""
tests/benchmark_forecasting.py
-------------------------------
Reproducible Empirical Benchmark for ML Demand Forecasting Module.
Evaluates MAE, RMSE, and Baseline Comparison.
"""

import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.demand_dataset import generate_synthetic_demand_dataset
from app.demand_forecaster import FacilityDemandForecaster

def run_forecasting_benchmark():
    print("=" * 70)
    print("[*] RUNNING ML FACILITY DEMAND FORECASTING BENCHMARK")
    print("=" * 70)

    df = generate_synthetic_demand_dataset(days=365, seed=42)
    print(f"[+] Generated synthetic dataset: {len(df)} records across 365 days.")

    forecaster = FacilityDemandForecaster()
    metrics = forecaster.train(df)

    print(f"[+] Model Evaluation Results (Test Set 20%):")
    print(f"    - ML GradientBoosting MAE:  {metrics['test_mae']}% occupancy")
    print(f"    - ML GradientBoosting RMSE: {metrics['test_rmse']}% occupancy")
    print(f"    - Historical Mean Base MAE: {metrics['baseline_mae']}% occupancy")
    print(f"    - Historical Mean Base RMSE:{metrics['baseline_rmse']}% occupancy")
    print(f"    - Relative MAE Improvement: {metrics['mae_improvement_pct']}%")

    with open("forecast_benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    print(f"\n[+] Saved forecasting benchmark to forecast_benchmark_results.json")

if __name__ == "__main__":
    run_forecasting_benchmark()
