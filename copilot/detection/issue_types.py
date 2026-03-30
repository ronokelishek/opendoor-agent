"""
detection/issue_types.py
------------------------
Defines the taxonomy of business issues detected by the copilot
and the Issue dataclass used throughout the system.

Issue types map to business domains with clear ownership:
  PRICING_MISALIGNMENT  → pricing team
  INVENTORY_AGING       → market-ops team
  FUNNEL_DETERIORATION  → growth team
  MARGIN_COMPRESSION    → pricing team
"""

from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
# Issue type taxonomy
# ---------------------------------------------------------------------------

ISSUE_TYPES = {

    "PRICING_MISALIGNMENT": {
        "name": "Pricing Misalignment",
        "description": (
            "Opendoor's offer prices are deviating materially from market "
            "estimated values. When offers run above market, seller acceptance "
            "initially stays high but acquisition margins erode; when offers "
            "run below market, acceptance rates fall and volume suffers."
        ),
        "owner": "pricing",
        "severity_levels": ["low", "medium", "high", "critical"],
        "detection_signal": "avg_offer_vs_market_pct > threshold AND acceptance_rate falling",
        "typical_resolution_days": 7,
        "escalation_path": "Pricing Analyst → Pricing Lead → VP Pricing",
    },

    "INVENTORY_AGING": {
        "name": "Inventory Aging",
        "description": (
            "A growing share of Opendoor's active inventory has exceeded 90 days "
            "on market, or average DOM is rising consistently week-over-week. "
            "Aged inventory compresses resale margins and ties up working capital."
        ),
        "owner": "market-ops",
        "severity_levels": ["low", "medium", "high", "critical"],
        "detection_signal": "aging_inventory_rate > 15% OR avg_dom increasing 2+ consecutive weeks",
        "typical_resolution_days": 14,
        "escalation_path": "Market Ops Analyst → Market Ops Lead → VP Operations",
    },

    "FUNNEL_DETERIORATION": {
        "name": "Funnel Deterioration",
        "description": (
            "Conversion rates within the seller funnel are declining. "
            "Lead-to-offer drops indicate top-of-funnel friction; "
            "offer-to-close drops indicate late-stage execution issues. "
            "Either pattern reduces transaction volume and revenue efficiency."
        ),
        "owner": "growth",
        "severity_levels": ["low", "medium", "high", "critical"],
        "detection_signal": "lead_to_offer_rate WoW drop > 3% OR offer_to_close_rate WoW drop > 4%",
        "typical_resolution_days": 10,
        "escalation_path": "Growth Analyst → Growth Lead → VP Growth",
    },

    "MARGIN_COMPRESSION": {
        "name": "Margin Compression",
        "description": (
            "Estimated acquisition margins are falling materially week-over-week. "
            "This is an early warning before realized resale margins compress, "
            "giving the pricing team a window to recalibrate before losses accrue."
        ),
        "owner": "pricing",
        "severity_levels": ["low", "medium", "high", "critical"],
        "detection_signal": "avg_acquisition_margin WoW drop > 2 percentage points",
        "typical_resolution_days": 7,
        "escalation_path": "Pricing Analyst → Pricing Lead → VP Pricing",
    },
}


# ---------------------------------------------------------------------------
# Issue dataclass
# ---------------------------------------------------------------------------

@dataclass
class Issue:
    """
    Represents a single detected business issue.

    Attributes:
        issue_id:         Unique identifier (e.g., "PRICING_MISALIGNMENT_Phoenix_mid_tier_2024-12-09")
        issue_type:       Key from ISSUE_TYPES dict
        market:           Geographic market (e.g., "Phoenix")
        segment:          Home segment (e.g., "mid_tier")
        severity:         One of: "low", "medium", "high", "critical"
        week_start:       ISO date string of the detection week
        title:            Short human-readable title for reports and alerts
        evidence:         List of bullet-point strings supporting the detection
        metrics_snapshot: Current metric values at time of detection
        wow_deltas:       Week-over-week changes for key metrics
        confidence:       "High", "Medium-High", or "Medium"
        owner:            Team responsible for resolution
    """

    issue_id: str
    issue_type: str
    market: str
    segment: str
    severity: str           # "low" | "medium" | "high" | "critical"
    week_start: str         # ISO date string, e.g. "2024-12-09"
    title: str
    evidence: List[str] = field(default_factory=list)
    metrics_snapshot: dict = field(default_factory=dict)
    wow_deltas: dict = field(default_factory=dict)
    confidence: str = "Medium"   # "High" | "Medium-High" | "Medium"
    owner: str = ""

    def __post_init__(self):
        """Validate and auto-populate owner from ISSUE_TYPES if not provided."""
        if not self.owner and self.issue_type in ISSUE_TYPES:
            self.owner = ISSUE_TYPES[self.issue_type]["owner"]

        valid_severities = ["low", "medium", "high", "critical"]
        if self.severity not in valid_severities:
            raise ValueError(
                f"Invalid severity '{self.severity}'. Must be one of {valid_severities}."
            )

        valid_confidences = ["High", "Medium-High", "Medium"]
        if self.confidence not in valid_confidences:
            raise ValueError(
                f"Invalid confidence '{self.confidence}'. Must be one of {valid_confidences}."
            )

    def to_dict(self) -> dict:
        """Serialize to a plain dict for JSON output."""
        return {
            "issue_id": self.issue_id,
            "issue_type": self.issue_type,
            "market": self.market,
            "segment": self.segment,
            "severity": self.severity,
            "week_start": self.week_start,
            "title": self.title,
            "evidence": self.evidence,
            "metrics_snapshot": self.metrics_snapshot,
            "wow_deltas": self.wow_deltas,
            "confidence": self.confidence,
            "owner": self.owner,
        }

    def severity_rank(self) -> int:
        """Numeric severity rank for sorting (higher = more severe)."""
        return {"low": 1, "medium": 2, "high": 3, "critical": 4}[self.severity]


# ---------------------------------------------------------------------------
# Severity assignment helpers
# ---------------------------------------------------------------------------

def assign_severity(value: float, warn: float, critical: float) -> str:
    """
    Assign a severity level based on how far a value exceeds thresholds.

    For metrics where larger magnitude = worse (e.g., drops expressed as
    positive numbers, or rates expressed as excess above threshold).

    Args:
        value:    The metric deviation (e.g., WoW drop as positive float)
        warn:     Threshold for "medium" severity
        critical: Threshold for "high" severity

    Returns:
        "critical" if value > 2x critical threshold
        "high"     if value >= critical threshold
        "medium"   if value >= warn threshold
        "low"      otherwise
    """
    if value >= critical * 2:
        return "critical"
    elif value >= critical:
        return "high"
    elif value >= warn:
        return "medium"
    else:
        return "low"
