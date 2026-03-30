"""
metrics/definitions.py
----------------------
Business metric layer for the Opendoor Pricing & Conversion Copilot.

Each metric definition includes:
  - formula:           Human-readable computation description
  - description:       What the metric measures
  - warn_threshold:    Threshold for a yellow/warning alert
  - critical_threshold: Threshold for a red/critical alert
  - owner:             Team responsible for this metric
  - business_context:  LLM-friendly explanation of why this matters

ISSUE_THRESHOLDS contains numeric constants used by detection/rules.py
so there is a single source of truth for all threshold values.
"""

# ---------------------------------------------------------------------------
# Metric Definitions
# ---------------------------------------------------------------------------

METRIC_DEFINITIONS = {

    "offer_acceptance_rate": {
        "formula": "accepted_offer_count / offer_count",
        "description": (
            "Percentage of Opendoor offers that sellers accept. "
            "The primary signal of offer competitiveness vs. market."
        ),
        "warn_threshold": "WoW drop > 5%",
        "critical_threshold": "WoW drop > 10%, or rate below 50%",
        "unit": "ratio",
        "owner": "pricing",
        "business_context": (
            "A falling acceptance rate is the first indicator that Opendoor's "
            "offers are out of step with seller expectations or market conditions. "
            "In a balanced market, acceptance rates typically run 60-75%. "
            "A sustained drop signals the pricing model needs recalibration."
        ),
    },

    "lead_to_offer_rate": {
        "formula": "offer_count / lead_count",
        "description": (
            "Percentage of incoming seller leads that progress to a formal offer. "
            "Measures top-of-funnel conversion efficiency."
        ),
        "warn_threshold": "WoW drop > 3%",
        "critical_threshold": "WoW drop > 6%, or rate below 40%",
        "unit": "ratio",
        "owner": "growth",
        "business_context": (
            "A declining lead-to-offer rate suggests friction in the offer "
            "generation process — either leads are lower quality, the product "
            "experience is degrading, or operational capacity is constrained. "
            "Should be monitored alongside marketing spend efficiency."
        ),
    },

    "offer_to_close_rate": {
        "formula": "close_count / accepted_offer_count",
        "description": (
            "Percentage of accepted offers that reach final close. "
            "Measures late-funnel execution quality."
        ),
        "warn_threshold": "WoW drop > 4%",
        "critical_threshold": "WoW drop > 8%, or rate below 55%",
        "unit": "ratio",
        "owner": "operations",
        "business_context": (
            "Offer-to-close drop-off often signals operational issues: "
            "title/escrow problems, buyer financing failures, or inspection "
            "contingencies not being cleared. A decline here is expensive "
            "because Opendoor has already committed resources."
        ),
    },

    "avg_offer_vs_market_pct": {
        "formula": "(opendoor_offer_price - market_estimated_value) / market_estimated_value",
        "description": (
            "Average percentage difference between Opendoor's offer price and "
            "the third-party market estimated value. Positive = Opendoor is "
            "offering above market; negative = below market."
        ),
        "warn_threshold": "Value > +2% or < -5%",
        "critical_threshold": "Value > +4% or < -8%",
        "unit": "pct",
        "owner": "pricing",
        "business_context": (
            "This metric captures pricing model accuracy relative to market. "
            "Offers > 4% above market suggest the model is overvaluing homes, "
            "which compresses acquisition margins and erodes profitability. "
            "Offers too far below market kill acceptance rates and volume."
        ),
    },

    "aging_inventory_rate": {
        "formula": "count(inventory_days_on_market > 90) / inventory_count",
        "description": (
            "Share of active inventory that has been on market more than 90 days. "
            "A leading indicator of resale difficulty and potential markdowns."
        ),
        "warn_threshold": "Rate > 15%",
        "critical_threshold": "Rate > 20%, or increasing 3+ consecutive weeks",
        "unit": "ratio",
        "owner": "market-ops",
        "business_context": (
            "Aging inventory ties up capital and typically requires price "
            "reductions to clear, compressing resale margins. In a healthy "
            "market, <10% of inventory should exceed 90 DOM. Rates above 15% "
            "suggest the local market has softened or acquisition pricing "
            "was too aggressive on certain home profiles."
        ),
    },

    "avg_days_on_market": {
        "formula": "mean(inventory_days_on_market)",
        "description": (
            "Average number of days Opendoor's active listings have been on market. "
            "Simpler complement to aging_inventory_rate."
        ),
        "warn_threshold": "WoW increase > 5 days",
        "critical_threshold": "WoW increase > 10 days, or absolute value > 60",
        "unit": "days",
        "owner": "market-ops",
        "business_context": (
            "Rising DOM is a lagging indicator of demand softness. "
            "Combined with inventory aging rate it confirms whether a market "
            "is experiencing a broad slowdown or isolated pockets of overpriced homes."
        ),
    },

    "avg_acquisition_margin": {
        "formula": "mean(acquisition_margin_estimate)",
        "description": (
            "Average estimated gross margin on homes currently being acquired. "
            "Expressed as a percentage of acquisition price."
        ),
        "warn_threshold": "WoW drop > 1 percentage point",
        "critical_threshold": "WoW drop > 2 percentage points, or absolute value < 2%",
        "unit": "pct",
        "owner": "pricing",
        "business_context": (
            "Acquisition margin is the primary profitability lever. "
            "A margin below 2% leaves insufficient buffer for holding costs, "
            "transaction fees, and unexpected repairs. Compression here "
            "often follows from offer prices drifting above market estimates."
        ),
    },

    "avg_resale_margin": {
        "formula": "mean(resale_margin_estimate)",
        "description": (
            "Average realized gross margin on homes sold in the period. "
            "Reflects actual market conditions at time of resale."
        ),
        "warn_threshold": "WoW drop > 1.5 percentage points",
        "critical_threshold": "WoW drop > 3 percentage points, or absolute value < 3%",
        "unit": "pct",
        "owner": "market-ops",
        "business_context": (
            "Resale margin is the realized outcome of the pricing strategy. "
            "A widening gap between acquisition margin estimate and realized "
            "resale margin signals the AVM (automated valuation model) is "
            "systematically overestimating home values in a given market."
        ),
    },

    "funnel_efficiency": {
        "formula": "close_count / lead_count",
        "description": (
            "End-to-end funnel conversion from initial lead to closed transaction. "
            "Composite metric capturing all conversion stages simultaneously."
        ),
        "warn_threshold": "WoW drop > 2%",
        "critical_threshold": "WoW drop > 5%, or absolute value < 15%",
        "unit": "ratio",
        "owner": "growth",
        "business_context": (
            "Funnel efficiency captures the overall health of the conversion "
            "pipeline in a single number. A drop here without a corresponding "
            "drop in lead volume implies conversion is the constraint, not "
            "demand — pointing to pricing, product, or ops issues."
        ),
    },
}


# ---------------------------------------------------------------------------
# Issue Detection Thresholds
# ---------------------------------------------------------------------------
# Single source of truth — detection/rules.py imports these constants.

ISSUE_THRESHOLDS = {

    # Pricing misalignment
    "PRICING_OFFER_VS_MARKET_WARN":     0.02,   # 2% above market → warning
    "PRICING_OFFER_VS_MARKET_CRITICAL": 0.04,   # 4% above market → critical
    "PRICING_ACCEPTANCE_DROP_WARN":     0.05,   # 5% WoW drop in acceptance rate
    "PRICING_ACCEPTANCE_DROP_CRITICAL": 0.10,   # 10% WoW drop

    # Inventory aging
    "AGING_RATE_WARN":                  0.15,   # 15% of inventory > 90 DOM
    "AGING_RATE_CRITICAL":              0.20,   # 20% of inventory > 90 DOM
    "AGING_DOM_INCREASE_WARN":          5.0,    # 5 days WoW DOM increase
    "AGING_DOM_THRESHOLD_DAYS":         90,     # Days to classify home as "aged"

    # Funnel deterioration
    "FUNNEL_L2O_DROP_WARN":             0.03,   # 3% WoW lead-to-offer drop
    "FUNNEL_L2O_DROP_CRITICAL":         0.06,   # 6% WoW drop
    "FUNNEL_O2C_DROP_WARN":             0.04,   # 4% WoW offer-to-close drop
    "FUNNEL_O2C_DROP_CRITICAL":         0.08,   # 8% WoW drop

    # Margin compression
    "MARGIN_ACQ_DROP_WARN":             0.01,   # 1pp WoW acquisition margin drop
    "MARGIN_ACQ_DROP_CRITICAL":         0.02,   # 2pp WoW drop
    "MARGIN_ACQ_ABS_CRITICAL":          0.02,   # Absolute acquisition margin < 2%
}
