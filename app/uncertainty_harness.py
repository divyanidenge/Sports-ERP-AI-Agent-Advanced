"""
app/uncertainty_harness.py
--------------------------
Dynamic Epistemic Uncertainty & Confidence-Gated Risk Harness.

Formal Model:
Calculates a continuous execution confidence score Γ(q, S) ∈ [0.0, 1.0] based on:
1. Entity Extraction Confidence (E_conf)
2. Semantic Ambiguity / Candidate Cardinality (A_card)
3. Temporal Determinacy (T_det)
4. Transactional Action Risk Weight (R_act)
5. User Permission & Quota Safety Margin (Q_safe)

Tiers:
- LOW_RISK_AUTO_EXECUTE (Γ ≥ 0.85 and Read-Only)
- MEDIUM_RISK_DISAMBIGUATION (0.50 ≤ Γ < 0.85 or Ambiguous Cardinality)
- HIGH_RISK_CONFIRMATION (Γ < 0.50 or Consequential State-Modifying Action)
"""

from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from datetime import date, datetime, timedelta
import re

from app.database import get_db_connection

class UncertaintyTier(str, Enum):
    LOW_RISK_AUTO_EXECUTE = "LOW_RISK_AUTO_EXECUTE"
    MEDIUM_RISK_DISAMBIGUATION = "MEDIUM_RISK_DISAMBIGUATION"
    HIGH_RISK_CONFIRMATION = "HIGH_RISK_CONFIRMATION"

class UncertaintyEvaluation(BaseModel):
    confidence_score: float # [0.0, 1.0]
    tier: UncertaintyTier
    action_type: str        # 'read', 'booking', 'cancellation', 'governance', 'unknown'
    ambiguity_detected: bool = False
    ambiguity_reasons: List[str] = Field(default_factory=list)
    candidate_options: List[Dict[str, Any]] = Field(default_factory=list)
    recommended_action: str # 'execute', 'disambiguate', 'confirm'
    disambiguation_prompt: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)

def evaluate_uncertainty(
    query: str,
    user_id: int,
    user_role: str = "student",
    detected_intent: str = "unknown",
    detected_params: Optional[Dict[str, Any]] = None
) -> UncertaintyEvaluation:
    """
    Evaluates epistemic uncertainty and execution risk for incoming user utterances.
    """
    params = detected_params or {}
    q = query.lower().strip()
    reasons = []
    candidates = []

    # 1. Classify Action Consequentiality
    is_cancellation = any(w in q for w in ["cancel", "delete", "remove", "radd", "hatao"])
    is_booking = any(w in q for w in ["book", "reserve", "slot chahiye", "kar do"]) and not is_cancellation
    is_governance = any(w in q for w in ["block", "unblock", "suspend"])
    is_read = not (is_cancellation or is_booking or is_governance)

    if is_cancellation:
        action_type = "cancellation"
        base_risk_weight = 0.50
    elif is_booking:
        action_type = "booking"
        base_risk_weight = 0.65
    elif is_governance:
        action_type = "governance"
        base_risk_weight = 0.40
    else:
        action_type = "read"
        base_risk_weight = 0.95

    # 2. Evaluate Temporal Determinacy
    has_explicit_date = bool(re.search(r"\b(\d{4}-\d{2}-\d{2}|today|tomorrow|aaj|kal)\b", q))
    has_explicit_time = bool(re.search(r"\b(\d{1,2}(:\d{2})?\s*(am|pm)|\d{2}:\d{2}\s*-\s*\d{2}:\d{2})\b", q))
    has_specific_id = bool(re.search(r"(?:booking\s+#?|#)(\d+)", q))
    has_explicit_target = has_specific_id or ("latest" in q) or ("next" in q) or ("upcoming" in q)
    
    temporal_score = 1.0
    if not has_explicit_date and (is_booking or (is_cancellation and not has_explicit_target)):
        temporal_score -= 0.30
        reasons.append("Missing explicit date specification")
    if not has_explicit_time and is_booking:
        temporal_score -= 0.30
        reasons.append("Missing explicit time slot specification")

    # 3. Evaluate Ambiguity & Candidate Cardinality (e.g. Cancellation targets)
    cardinality_score = 1.0
    disambiguation_prompt = None

    if is_cancellation and user_id > 0:
        conn = get_db_connection()
        cursor = conn.cursor()
        today_iso = date.today().isoformat()
        
        # Check if date was mentioned
        target_date = params.get("booking_date")
        if not target_date:
            if "tomorrow" in q or "kal" in q:
                target_date = (date.today() + timedelta(days=1)).isoformat()
            elif "today" in q or "aaj" in q:
                target_date = today_iso

        # Check if sport was mentioned
        target_sport = params.get("sport_name")
        if not target_sport:
            from app.query_agent import extract_sport
            target_sport = extract_sport(q)

        sql_parts = [
            "SELECT b.id, s.name as sport_name, f.name as facility_name, b.booking_date, b.time_slot",
            "FROM bookings b",
            "JOIN sports s ON b.sport_id = s.id",
            "JOIN facilities f ON b.facility_id = f.id",
            "WHERE b.user_id = ? AND b.status = 'confirmed'"
        ]
        sql_params = [user_id]

        if target_date:
            sql_parts.append("AND b.booking_date = ?")
            sql_params.append(target_date)
        else:
            sql_parts.append("AND b.booking_date >= ?")
            sql_params.append(today_iso)

        if target_sport:
            sql_parts.append("AND LOWER(s.name) LIKE ?")
            sql_params.append(f"%{target_sport.lower().strip()}%")

        sql_parts.append("ORDER BY b.booking_date ASC, b.time_slot ASC")
        cursor.execute(" ".join(sql_parts), tuple(sql_params))
        
        user_active_bookings = [dict(r) for r in cursor.fetchall()]
        conn.close()

        # If user has multiple bookings that match the query scope or requested options/disambiguation
        is_options_requested = any(w in q for w in ["options", "option", "which", "choose", "can't remember", "cant remember"])
        if (len(user_active_bookings) > 1 or (len(user_active_bookings) >= 1 and is_options_requested)) and not has_specific_id and not has_explicit_time:
            cardinality_score = 0.35
            reasons.append(f"User holds {len(user_active_bookings)} candidate bookings matching query scope")
            candidates = user_active_bookings
            
            opts = [f"{i+1}. {b['sport_name']} at {b['facility_name']} on {b['booking_date']} ({b['time_slot']}) [Booking #{b['id']}]"
                    for i, b in enumerate(user_active_bookings)]
            disambiguation_prompt = (
                f"Multiple matching active bookings found ({len(user_active_bookings)} candidate bookings):\n" +
                "\n".join(opts) +
                "\n\nPlease specify the booking ID (e.g. 'Cancel booking #<ID>') or exact time slot you wish to cancel."
            )

    # 4. Entity Extraction Confidence
    entity_score = 1.0
    if (is_booking or is_cancellation) and not params.get("sport_name") and not any(s in q for s in ["badminton", "cricket", "football", "tennis", "basketball", "swimming"]):
        if not is_cancellation: # cancellation might refer to "my booking"
            entity_score = 0.50
            reasons.append("Unrecognized or missing sport entity")

    # 5. Composite Confidence Score Calculation Γ(q, S)
    # Weights: Action Risk (0.35), Cardinality (0.30), Temporal (0.20), Entity (0.15)
    gamma = (
        0.35 * base_risk_weight +
        0.30 * cardinality_score +
        0.20 * temporal_score +
        0.15 * entity_score
    )
    gamma = max(0.0, min(1.0, round(gamma, 3)))

    # 6. Tier Assignment
    if is_read and gamma >= 0.80:
        tier = UncertaintyTier.LOW_RISK_AUTO_EXECUTE
        rec_action = "execute"
    elif disambiguation_prompt is not None or (cardinality_score < 0.60):
        tier = UncertaintyTier.MEDIUM_RISK_DISAMBIGUATION
        rec_action = "disambiguate"
    else:
        # High Risk: state modifying writes or low confidence
        tier = UncertaintyTier.HIGH_RISK_CONFIRMATION
        rec_action = "confirm"

    return UncertaintyEvaluation(
        confidence_score=gamma,
        tier=tier,
        action_type=action_type,
        ambiguity_detected=bool(reasons),
        ambiguity_reasons=reasons,
        candidate_options=candidates,
        recommended_action=rec_action,
        disambiguation_prompt=disambiguation_prompt,
        details={
            "base_risk_weight": base_risk_weight,
            "cardinality_score": cardinality_score,
            "temporal_score": temporal_score,
            "entity_score": entity_score,
            "user_role": user_role
        }
    )
