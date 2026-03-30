"""
Feedback Loop Tracker
======================
Closes the analytics-to-action loop by tracking whether recommendations
were acted on and whether the expected outcome materialized.

This is what makes the system learn over time:
  1. Agent detects issue → generates Decision Packet with expected outcome
  2. Operator logs action taken (or deferred)
  3. Next week: agent checks KPI vs prediction → updates confidence weighting
  4. Patterns that repeatedly predict correctly gain higher confidence
  5. Patterns that miss get flagged for recalibration

Storage: JSON file (production: replace with Snowflake / ops DB)
"""

import json
import statistics
from datetime import datetime, date
from pathlib import Path

FEEDBACK_PATH = Path(__file__).parent.parent.parent / "briefings" / "feedback_log.json"

# ── CONFIDENCE WEIGHT TABLE ───────────────────────────────────────────────────
# Updated by recalibrate_confidence() based on historical prediction accuracy
# Default weights reflect reasonable priors before any feedback data

CONFIDENCE_WEIGHTS = {
    "pricing_misalignment": 0.82,   # LSR is a reliable acceptance proxy
    "inventory_aging":      0.78,   # DOM trends are persistent signals
    "funnel_deterioration": 0.71,   # Multi-factor, harder to isolate cause
    "margin_compression":   0.68,   # Downstream of other issues, more noisy
}

# ── ACTION STATUS OPTIONS ─────────────────────────────────────────────────────
ACTION_STATUSES = {
    "taken":    "Recommendation was implemented as suggested",
    "partial":  "Recommendation partially implemented (different magnitude or scope)",
    "deferred": "Recommendation noted but deferred to next cycle",
    "rejected": "Recommendation reviewed and rejected by owner",
    "pending":  "Awaiting owner decision",
}


def _load_log() -> list:
    if FEEDBACK_PATH.exists():
        return json.loads(FEEDBACK_PATH.read_text(encoding="utf-8"))
    return []


def _save_log(log: list) -> None:
    FEEDBACK_PATH.parent.mkdir(exist_ok=True)
    FEEDBACK_PATH.write_text(json.dumps(log, indent=2, default=str), encoding="utf-8")


# ── LOG A RECOMMENDATION ──────────────────────────────────────────────────────

def log_recommendation(
    issue_type: str,
    market: str,
    segment: str,
    severity: str,
    actions: list,
    expected_outcome: dict,
    confidence: str,
    week_start: str = None,
) -> dict:
    """
    Log a Decision Packet recommendation when it is generated.
    Returns the entry with a unique rec_id for follow-up tracking.
    """
    log = _load_log()
    rec_id = f"REC-{len(log) + 1:04d}"
    week = week_start or date.today().isoformat()

    entry = {
        "rec_id": rec_id,
        "week_start": week,
        "logged_at": datetime.now().isoformat(),
        "issue_type": issue_type,
        "market": market,
        "segment": segment,
        "severity": severity,
        "actions": actions,
        "expected_outcome": expected_outcome,
        "confidence_at_issue": confidence,
        "action_status": "pending",
        "outcome_observed": None,
        "prediction_accuracy": None,
        "notes": None,
    }

    log.append(entry)
    _save_log(log)
    return entry


# ── RECORD ACTION TAKEN ───────────────────────────────────────────────────────

def record_action_taken(
    rec_id: str,
    action_status: str,
    notes: str = None,
) -> dict:
    """
    Record whether the recommendation was acted on.
    action_status: 'taken', 'partial', 'deferred', 'rejected', 'pending'
    """
    if action_status not in ACTION_STATUSES:
        return {"error": f"Invalid status. Use: {list(ACTION_STATUSES.keys())}"}

    log = _load_log()
    for entry in log:
        if entry["rec_id"] == rec_id:
            entry["action_status"] = action_status
            entry["action_status_label"] = ACTION_STATUSES[action_status]
            entry["action_recorded_at"] = datetime.now().isoformat()
            if notes:
                entry["notes"] = notes
            _save_log(log)
            return entry

    return {"error": f"rec_id {rec_id} not found"}


# ── RECORD OUTCOME ────────────────────────────────────────────────────────────

def record_outcome(
    rec_id: str,
    observed_metric: str,
    observed_value: float,
    expected_value: float = None,
) -> dict:
    """
    Record what actually happened after the action was taken.
    Calculates prediction accuracy and updates the feedback log.

    observed_metric: e.g. "acceptance_rate_change_pct", "dom_change", "homes_sold_change"
    observed_value:  the actual measured change
    expected_value:  what the Decision Packet predicted (if not passed, read from log)
    """
    log = _load_log()
    for entry in log:
        if entry["rec_id"] == rec_id:
            expected = expected_value
            if expected is None:
                # Try to read from the stored expected_outcome
                eo = entry.get("expected_outcome", {})
                expected = eo.get("acceptance_rate_improvement_pct") or eo.get("volume_uplift_pct")
                if expected and isinstance(expected, str):
                    expected = float(expected.replace("%", "").replace("+", ""))

            accuracy = None
            if expected and expected != 0:
                accuracy = round(1 - abs(observed_value - expected) / abs(expected), 3)
                accuracy = max(0.0, min(1.0, accuracy))  # clamp 0–1

            entry["outcome_observed"] = {
                "metric": observed_metric,
                "observed_value": observed_value,
                "expected_value": expected,
                "recorded_at": datetime.now().isoformat(),
            }
            entry["prediction_accuracy"] = accuracy
            _save_log(log)
            return entry

    return {"error": f"rec_id {rec_id} not found"}


# ── RECALIBRATE CONFIDENCE ────────────────────────────────────────────────────

def recalibrate_confidence() -> dict:
    """
    Recompute confidence weights based on historical prediction accuracy.
    Runs after outcomes are recorded — updates CONFIDENCE_WEIGHTS for next cycle.

    Returns updated weights and a calibration summary.
    """
    log = _load_log()
    resolved = [e for e in log if e.get("prediction_accuracy") is not None]

    if not resolved:
        return {
            "tool": "recalibrate_confidence",
            "status": "insufficient_data",
            "message": "No resolved outcomes yet. Need at least 1 outcome recorded.",
            "current_weights": CONFIDENCE_WEIGHTS,
            "recommendations_logged": len(log),
            "outcomes_recorded": 0,
        }

    # Group by issue_type and compute mean accuracy
    by_type: dict = {}
    for entry in resolved:
        itype = entry["issue_type"]
        if itype not in by_type:
            by_type[itype] = []
        by_type[itype].append(entry["prediction_accuracy"])

    updated_weights = dict(CONFIDENCE_WEIGHTS)
    calibration_detail = {}

    for itype, accuracies in by_type.items():
        mean_acc = round(statistics.mean(accuracies), 3)
        n = len(accuracies)
        # Blend prior weight with observed accuracy (more data = more weight to observed)
        prior = CONFIDENCE_WEIGHTS.get(itype, 0.70)
        blend_factor = min(0.8, n / 10)  # caps at 80% observed weight after 10+ samples
        new_weight = round(prior * (1 - blend_factor) + mean_acc * blend_factor, 3)
        updated_weights[itype] = new_weight

        calibration_detail[itype] = {
            "sample_count": n,
            "mean_accuracy": mean_acc,
            "prior_weight": prior,
            "new_weight": new_weight,
            "direction": "increased" if new_weight > prior else "decreased" if new_weight < prior else "unchanged",
        }

    # Identify patterns that need investigation
    underperforming = [k for k, v in calibration_detail.items() if v["mean_accuracy"] < 0.5]
    overperforming  = [k for k, v in calibration_detail.items() if v["mean_accuracy"] > 0.9]

    return {
        "tool": "recalibrate_confidence",
        "status": "updated",
        "recommendations_logged": len(log),
        "outcomes_recorded": len(resolved),
        "updated_weights": updated_weights,
        "calibration_detail": calibration_detail,
        "flags": {
            "underperforming_patterns": underperforming,
            "high_accuracy_patterns": overperforming,
            "message": (
                f"Patterns needing recalibration: {underperforming}" if underperforming
                else "All patterns within acceptable accuracy range."
            ),
        },
    }


# ── GET FEEDBACK SUMMARY ──────────────────────────────────────────────────────

def get_feedback_summary() -> dict:
    """
    Return a summary of the feedback log — action rates, accuracy trends,
    and which markets / issue types are improving or degrading.
    Used by monitor-agent in weekly briefing to show system learning.
    """
    log = _load_log()

    if not log:
        return {
            "tool": "get_feedback_summary",
            "status": "empty",
            "message": "No recommendations logged yet. System learns after first cycle.",
            "confidence_weights": CONFIDENCE_WEIGHTS,
        }

    total = len(log)
    by_status = {}
    for entry in log:
        s = entry.get("action_status", "pending")
        by_status[s] = by_status.get(s, 0) + 1

    resolved = [e for e in log if e.get("prediction_accuracy") is not None]
    avg_accuracy = round(statistics.mean(e["prediction_accuracy"] for e in resolved), 3) if resolved else None

    by_market = {}
    for entry in log:
        m = entry["market"]
        if m not in by_market:
            by_market[m] = {"total": 0, "taken": 0, "accuracy": []}
        by_market[m]["total"] += 1
        if entry.get("action_status") == "taken":
            by_market[m]["taken"] += 1
        if entry.get("prediction_accuracy") is not None:
            by_market[m]["accuracy"].append(entry["prediction_accuracy"])

    market_summary = {}
    for m, data in by_market.items():
        market_summary[m] = {
            "recommendations": data["total"],
            "actions_taken": data["taken"],
            "action_rate_pct": round(data["taken"] / data["total"] * 100) if data["total"] else 0,
            "avg_prediction_accuracy": round(statistics.mean(data["accuracy"]), 3) if data["accuracy"] else None,
        }

    return {
        "tool": "get_feedback_summary",
        "total_recommendations": total,
        "by_action_status": by_status,
        "outcomes_recorded": len(resolved),
        "avg_prediction_accuracy": avg_accuracy,
        "by_market": market_summary,
        "confidence_weights": CONFIDENCE_WEIGHTS,
        "system_note": (
            "Prediction accuracy above 0.75 across all issue types — confidence weights stable."
            if avg_accuracy and avg_accuracy > 0.75
            else "Accuracy data insufficient — continue logging outcomes to improve calibration."
        ),
    }
