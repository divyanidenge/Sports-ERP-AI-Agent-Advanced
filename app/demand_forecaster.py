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

    def predict_all_sports_demand(
        self,
        booking_date: str,
        time_slot: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Forecasts demand across all campus sports facilities for a given date and time slot.
        """
        target_slot = time_slot or "18:00 - 19:00"
        campus_sports = ["Badminton", "Basketball", "Cricket", "Football", "Swimming", "Table Tennis"]
        
        predictions = []
        for sport in campus_sports:
            pred = self.predict_congestion(sport, booking_date, target_slot)
            predictions.append(pred)

        predictions.sort(key=lambda x: x["predicted_occupancy_pct"], reverse=True)
        highest = predictions[0]
        
        congested = [p for p in predictions if p["predicted_occupancy_pct"] >= 70.0]
        moderate = [p for p in predictions if 45.0 <= p["predicted_occupancy_pct"] < 70.0]
        low = [p for p in predictions if p["predicted_occupancy_pct"] < 45.0]
        lowest = predictions[-1]

        congested_names = ", ".join([f"{p['sport_name']} ({p['predicted_occupancy_pct']}%)" for p in congested]) if congested else "None"
        low_names = ", ".join([f"{p['sport_name']} ({p['predicted_occupancy_pct']}%)" for p in low]) if low else "None"

        lines = [
            f"📊 **Campus Facility Demand Forecast for {booking_date} ({target_slot})**:",
            f"• 🔥 **Highest Demand Facility:** {highest['sport_name']} ({highest['predicted_occupancy_pct']}% expected occupancy)",
            f"• ⚠️ **Congested Facilities (≥70%):** {congested_names}",
            f"• 🟢 **Quieter / Low Congestion Options:** {low_names}",
            "",
            "**Detailed Occupancy Predictions:**"
        ]
        for p in predictions:
            lines.append(f"• **{p['sport_name']}:** {p['predicted_occupancy_pct']}% ({p['congestion_level']})")

        msg = "\n".join(lines)

        return {
            "booking_date": booking_date,
            "time_slot": target_slot,
            "facilities": [
                {
                    "sport_name": p["sport_name"],
                    "predicted_occupancy_pct": p["predicted_occupancy_pct"],
                    "congestion_level": p["congestion_level"],
                    "recommended_alternative_slot": p["recommended_alternative_slot"]
                }
                for p in predictions
            ],
            "highest_demand": {
                "sport_name": highest["sport_name"],
                "predicted_occupancy_pct": highest["predicted_occupancy_pct"],
                "congestion_level": highest["congestion_level"]
            },
            "lowest_demand": {
                "sport_name": lowest["sport_name"],
                "predicted_occupancy_pct": lowest["predicted_occupancy_pct"],
                "congestion_level": lowest["congestion_level"]
            },
            "highest_demand_sport": highest["sport_name"],
            "highest_demand_occupancy_pct": highest["predicted_occupancy_pct"],
            "congested_sports": [p["sport_name"] for p in congested],
            "low_congestion_sports": [p["sport_name"] for p in low],
            "predictions": predictions,
            "advisory_message": msg
        }

    def predict_highest_demand(
        self,
        booking_date: str,
        time_slot: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Pinpoints the facility with the highest predicted booking demand and provides alternatives.
        """
        all_res = self.predict_all_sports_demand(booking_date, time_slot)
        highest_sport = all_res["highest_demand_sport"]
        highest_occ = all_res["highest_demand_occupancy_pct"]
        target_slot = all_res["time_slot"]
        
        top_pred = all_res["predictions"][0]
        msg = (
            f"🔥 **Highest Predicted Demand Facility**:\n"
            f"• **Facility / Sport:** {highest_sport}\n"
            f"• **Date & Slot:** {booking_date} ({target_slot})\n"
            f"• **Predicted Occupancy:** {highest_occ}% ({top_pred['congestion_level']})\n"
            f"• **Confidence Interval:** {top_pred['confidence_band'][0]:.1f}% – {top_pred['confidence_band'][1]:.1f}%\n"
            f"• **Recommendation:** Expect high peak rush. For less congestion, consider booking **{top_pred['recommended_alternative_slot']}** (~{top_pred['alternative_slot_occupancy_pct']}% occupancy)."
        )
        return {
            "booking_date": booking_date,
            "time_slot": target_slot,
            "sport_name": highest_sport,
            "predicted_occupancy_pct": highest_occ,
            "congestion_level": top_pred["congestion_level"],
            "confidence_band": top_pred["confidence_band"],
            "recommended_alternative_slot": top_pred["recommended_alternative_slot"],
            "alternative_slot_occupancy_pct": top_pred["alternative_slot_occupancy_pct"],
            "advisory_message": msg,
            "all_facility_rankings": all_res["predictions"]
        }

# Global forecaster singleton
forecaster = FacilityDemandForecaster()

def predict_facility_congestion_tool(
    sport_name: Optional[str] = None,
    booking_date: Optional[str] = None,
    time_slot: Optional[str] = None
) -> Dict[str, Any]:
    """
    Tool function for AI agent integration. Supports specific sport or all facilities forecast.
    """
    b_date = booking_date or (date.today() + timedelta(days=1)).isoformat()
    t_slot = time_slot or "18:00 - 19:00"

    if not sport_name or sport_name.lower() in ["all", "none", "facilities", "sports", "campus"]:
        res = forecaster.predict_all_sports_demand(b_date, t_slot)
    else:
        res = forecaster.predict_congestion(sport_name, b_date, t_slot)

    return {
        "success": True,
        "data": res,
        "message": res["advisory_message"]
    }

def predict_highest_demand_facility_tool(
    booking_date: Optional[str] = None,
    time_slot: Optional[str] = None
) -> Dict[str, Any]:
    """
    Tool function for determining the facility/sport with the highest predicted demand.
    """
    b_date = booking_date or (date.today() + timedelta(days=1)).isoformat()
    res = forecaster.predict_highest_demand(b_date, time_slot)
    return {
        "success": True,
        "data": res,
        "message": res["advisory_message"]
    }
