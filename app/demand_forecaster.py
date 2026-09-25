"""
app/demand_forecaster.py
-------------------------
Predictive Sports Facility Demand & Congestion Forecasting Model.

Model Architecture:
Supervised Regression (Gradient Boosting / Random Forest) trained on historical
and synthetic athletic facility reservation logs.

Features:
- Categorical: sport_name, time_slot, is_outdoor
- Temporal: hour, day_of_week, is_weekend, month, day_of_month
- Contextual: is_exam_period

Metrics:
- Mean Absolute Error (MAE)
- Root Mean Squared Error (RMSE)
- Baseline: Historical Mean Moving Average per (sport, hour, is_weekend)
"""

import os
import re
import math
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, date, timedelta
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline

from app.demand_dataset import generate_synthetic_demand_dataset
from app.sports_service import ALL_STANDARD_SLOTS

class FacilityDemandForecaster:
    """
    Trained predictive regressor for facility demand and court congestion estimation.
    """
    def __init__(self):
        self.model: Optional[Pipeline] = None
        self.baseline_lookup: Dict[Tuple[str, int, int], float] = {}
        self.train_mae: float = 0.0
        self.test_mae: float = 0.0
        self.test_rmse: float = 0.0
        self.baseline_mae: float = 0.0
        self.baseline_rmse: float = 0.0
        self.is_trained: bool = False

    def train(self, df: Optional[pd.DataFrame] = None) -> Dict[str, float]:
        """
        Trains the Gradient Boosting forecasting pipeline on the demand dataset with an 80/20 train/test split.
        """
        if df is None:
            df = generate_synthetic_demand_dataset()

        df["date_dt"] = pd.to_datetime(df["date"])
        df["month"] = df["date_dt"].dt.month
        df["day_of_month"] = df["date_dt"].dt.day

        # Compute Historical Mean Baseline lookup on training set
        split_idx = int(len(df) * 0.8)
        train_df = df.iloc[:split_idx].copy()
        test_df = df.iloc[split_idx].copy() if split_idx < len(df) else train_df.copy()
        test_df = df.iloc[split_idx:].copy()

        # Build baseline lookup
        baseline_group = train_df.groupby(["sport_name", "hour", "is_weekend"])["occupancy_pct"].mean().to_dict()
        self.baseline_lookup = baseline_group
        overall_mean = train_df["occupancy_pct"].mean()

        features = ["sport_name", "hour", "day_of_week", "is_weekend", "is_exam_period", "is_outdoor", "month", "day_of_month"]
        target = "occupancy_pct"

        X_train = train_df[features]
        y_train = train_df[target]
        X_test = test_df[features]
        y_test = test_df[target]

        categorical_cols = ["sport_name"]
        numeric_cols = ["hour", "day_of_week", "is_weekend", "is_exam_period", "is_outdoor", "month", "day_of_month"]

        preprocessor = ColumnTransformer(
            transformers=[
                ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_cols),
                ("num", "passthrough", numeric_cols)
            ]
        )

        regressor = GradientBoostingRegressor(
            n_estimators=100,
            learning_rate=0.1,
            max_depth=4,
            random_state=42
        )

        self.model = Pipeline(steps=[
            ("preprocessor", preprocessor),
            ("regressor", regressor)
        ])

        self.model.fit(X_train, y_train)
        self.is_trained = True

        # Evaluate on Test Set
        y_pred = self.model.predict(X_test)
        self.test_mae = round(float(mean_absolute_error(y_test, y_pred)), 3)
        self.test_rmse = round(float(math.sqrt(mean_squared_error(y_test, y_pred))), 3)

        # Baseline predictions
        y_base = [self.baseline_lookup.get((r["sport_name"], r["hour"], r["is_weekend"]), overall_mean) for _, r in test_df.iterrows()]
        self.baseline_mae = round(float(mean_absolute_error(y_test, y_base)), 3)
        self.baseline_rmse = round(float(math.sqrt(mean_squared_error(y_test, y_base))), 3)

        return {
            "test_mae": self.test_mae,
            "test_rmse": self.test_rmse,
            "baseline_mae": self.baseline_mae,
            "baseline_rmse": self.baseline_rmse,
            "mae_improvement_pct": round(((self.baseline_mae - self.test_mae) / self.baseline_mae) * 100, 2)
        }

    def predict_congestion(
        self,
        sport_name: str,
        booking_date: str,
        time_slot: str
    ) -> Dict[str, Any]:
        """
        Predicts facility congestion and suggests low-congestion alternatives.
        """
        if not self.is_trained:
            self.train()

        dt = datetime.strptime(booking_date, "%Y-%m-%d").date()
        m = re.search(r"(\d{1,2}):\d{2}", time_slot)
        hour = int(m.group(1)) if m else 17

        day_of_week = dt.weekday()
        is_weekend = int(day_of_week in [5, 6])
        is_exam_period = int(dt.month in [5, 12] and dt.day > 10)
        is_outdoor = int(sport_name.lower() in ["football", "cricket", "tennis"])

        input_df = pd.DataFrame([{
            "sport_name": sport_name.capitalize(),
            "hour": hour,
            "day_of_week": day_of_week,
            "is_weekend": is_weekend,
            "is_exam_period": is_exam_period,
            "is_outdoor": is_outdoor,
            "month": dt.month,
            "day_of_month": dt.day
        }])

        pred_occupancy = float(self.model.predict(input_df)[0])
        pred_occupancy = max(5.0, min(99.0, round(pred_occupancy, 1)))

        if pred_occupancy >= 75.0:
            congestion_level = "High / Peak Congestion"
        elif pred_occupancy >= 45.0:
            congestion_level = "Moderate Demand"
        else:
            congestion_level = "Low Congestion"

        # Search for optimal low-congestion alternative slot on the same date
        alt_slots = []
        for s in ALL_STANDARD_SLOTS:
            s_hour = int(re.search(r"(\d{1,2}):\d{2}", s).group(1))
            if s_hour == hour:
                continue
            alt_df = pd.DataFrame([{
                "sport_name": sport_name.capitalize(),
                "hour": s_hour,
                "day_of_week": day_of_week,
                "is_weekend": is_weekend,
                "is_exam_period": is_exam_period,
                "is_outdoor": is_outdoor,
                "month": dt.month,
                "day_of_month": dt.day
            }])
            alt_occ = float(self.model.predict(alt_df)[0])
            alt_slots.append((s, alt_occ))

        alt_slots.sort(key=lambda x: x[1])
        best_alt_slot = alt_slots[0][0] if alt_slots else "06:00 - 07:00"
        best_alt_occ = round(alt_slots[0][1], 1) if alt_slots else 30.0

        return {
            "sport_name": sport_name,
            "booking_date": booking_date,
            "time_slot": time_slot,
            "predicted_occupancy_pct": pred_occupancy,
            "congestion_level": congestion_level,
            "confidence_band": [max(0.0, pred_occupancy - self.test_mae), min(100.0, pred_occupancy + self.test_mae)],
            "recommended_alternative_slot": best_alt_slot,
            "alternative_slot_occupancy_pct": best_alt_occ,
            "advisory_message": f"Expected demand for {sport_name} on {booking_date} ({time_slot}) is {pred_occupancy}% ({congestion_level})." + (f" For quieter play, consider {best_alt_slot} (~{best_alt_occ}% expected occupancy)." if pred_occupancy >= 70.0 else "")
        }

# Global forecaster singleton
forecaster = FacilityDemandForecaster()

def predict_facility_congestion_tool(sport_name: str, booking_date: str, time_slot: str) -> Dict[str, Any]:
    """
    Tool function for AI agent integration.
    """
    res = forecaster.predict_congestion(sport_name, booking_date, time_slot)
    return {
        "success": True,
        "data": res,
        "message": res["advisory_message"]
    }
