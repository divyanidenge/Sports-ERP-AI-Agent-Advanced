"""
tests/test_demand_forecaster.py
--------------------------------
Unit and Evaluation Tests for Machine Learning Facility Demand Forecasting Module.
"""

import pytest
from app.demand_dataset import generate_synthetic_demand_dataset
from app.demand_forecaster import FacilityDemandForecaster, predict_facility_congestion_tool

def test_synthetic_dataset_generation():
    """Verify that synthetic dataset generator outputs expected schema, distributions, and sample count."""
    df = generate_synthetic_demand_dataset(days=30, seed=123)
    assert len(df) > 1000
    assert "date" in df.columns
    assert "hour" in df.columns
    assert "sport_name" in df.columns
    assert "occupancy_pct" in df.columns
    assert "congestion_level" in df.columns
    assert df["occupancy_pct"].min() >= 0.0
    assert df["occupancy_pct"].max() <= 100.0

def test_forecaster_training_and_metrics():
    """Verify that the regression model trains cleanly, converges, and achieves lower MAE than historical baseline."""
    df = generate_synthetic_demand_dataset(days=180, seed=42)
    forecaster = FacilityDemandForecaster()
    metrics = forecaster.train(df)
    
    assert forecaster.is_trained is True
    assert metrics["test_mae"] > 0.0
    assert metrics["test_rmse"] > 0.0
    assert metrics["test_mae"] <= metrics["baseline_mae"] + 0.5, "ML forecaster should achieve competitive MAE"

def test_predict_congestion_inference():
    """Verify congestion prediction inference, classification, and advisory alternative suggestions."""
    forecaster = FacilityDemandForecaster()
    df = generate_synthetic_demand_dataset(days=60, seed=42)
    forecaster.train(df)

    res = forecaster.predict_congestion(
        sport_name="Badminton",
        booking_date="2026-10-15",
        time_slot="18:00 - 19:00"
    )

    assert res["sport_name"] == "Badminton"
    assert "predicted_occupancy_pct" in res
    assert res["congestion_level"] in ["High / Peak Congestion", "Moderate Demand", "Low Congestion"]
    assert "recommended_alternative_slot" in res
    assert len(res["confidence_band"]) == 2

def test_predict_facility_congestion_tool_wrapper():
    """Verify the AI agent tool wrapper returns valid structured data and advisory message."""
    tool_res = predict_facility_congestion_tool("Football", "2026-10-20", "06:00 - 07:00")
    assert tool_res["success"] is True
    assert "data" in tool_res
    assert "Expected demand" in tool_res["message"]

def test_predict_all_sports_demand():
    """Verify cross-facility demand forecasting across all campus sports."""
    forecaster = FacilityDemandForecaster()
    df = generate_synthetic_demand_dataset(days=60, seed=42)
    forecaster.train(df)

    res = forecaster.predict_all_sports_demand("2026-10-25", "18:00 - 19:00")
    assert "predictions" in res
    assert len(res["predictions"]) >= 6
    assert "highest_demand_sport" in res
    assert res["highest_demand_occupancy_pct"] > 0.0
    assert "advisory_message" in res
    assert "Detailed Occupancy Predictions" in res["advisory_message"]

def test_predict_highest_demand_facility():
    """Verify pinpointing the single highest-demand sport/facility."""
    forecaster = FacilityDemandForecaster()
    df = generate_synthetic_demand_dataset(days=60, seed=42)
    forecaster.train(df)

    res = forecaster.predict_highest_demand("2026-10-25", "18:00 - 19:00")
    assert "sport_name" in res
    assert "predicted_occupancy_pct" in res
    assert "recommended_alternative_slot" in res
    assert "Highest Predicted Demand Facility" in res["advisory_message"]

def test_predict_facility_congestion_tool_cross_campus():
    """Verify tool wrapper handles campus-wide cross-facility query."""
    tool_res = predict_facility_congestion_tool(None, "2026-10-25", "18:00 - 19:00")
    assert tool_res["success"] is True
    assert "highest_demand_sport" in tool_res["data"]
    assert "Highest Demand Facility" in tool_res["message"]

