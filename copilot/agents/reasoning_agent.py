"""
agents/reasoning_agent.py
--------------------------
Claude API integration for the Opendoor Pricing & Conversion Copilot.

Sends detected issues to Claude for structured reasoning and action generation.
Falls back to high-quality pre-written mock responses when no API key is available,
enabling demo/testing without API access.

Architecture:
  analyze_issue(issue, use_mock) → dict
  analyze_all_issues(issues, use_mock) → list[dict]

Mock responses are written to the same quality standard as the prompt demands:
  specific, quantified, business-memo tone, with real numbers from the issue.
"""

import json
import os
from typing import Optional

from detection.issue_types import Issue
from agents.prompts import (
    SYSTEM_PROMPT,
    build_issue_reasoning_prompt,
    build_batch_summary_prompt,
)


# ---------------------------------------------------------------------------
# Live Claude API call
# ---------------------------------------------------------------------------

def _call_claude(system_prompt: str, user_prompt: str) -> dict:
    """
    Call Claude claude-opus-4-6 via the Anthropic SDK.

    Returns the parsed JSON response dict.
    Raises RuntimeError if the API call fails or response is not valid JSON.
    """
    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            "anthropic package not installed. Run: pip install anthropic"
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set.")

    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    response_text = message.content[0].text.strip()

    # Strip markdown code fences if model wraps in them
    if response_text.startswith("```"):
        lines = response_text.split("\n")
        response_text = "\n".join(lines[1:-1])

    try:
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Claude returned non-JSON response: {e}\nResponse: {response_text[:300]}"
        )


# ---------------------------------------------------------------------------
# Mock responses — pre-written per issue type
# ---------------------------------------------------------------------------

def _mock_pricing_misalignment(issue: Issue) -> dict:
    """High-quality mock for pricing misalignment issues."""
    snap = issue.metrics_snapshot
    offer_pct = snap.get("avg_offer_vs_market_pct", "N/A")
    acceptance = snap.get("offer_acceptance_rate", "N/A")
    offer_count = snap.get("offer_count", 0)
    acq_margin = snap.get("avg_acquisition_margin", "N/A")

    # Format for readability
    def pct(v):
        if v == "N/A" or v is None:
            return "N/A"
        return f"{float(v) * 100:.1f}%"

    offer_pct_str = pct(offer_pct)
    acceptance_str = pct(acceptance)
    acq_margin_str = pct(acq_margin)

    # Estimate missed closes
    missed_closes = int(offer_count * 0.12) if offer_count else 0

    return {
        "executive_summary": (
            f"Opendoor's offer prices in {issue.market} {issue.segment.replace('_', ' ')} are running "
            f"{offer_pct_str} above market estimated values, triggering a seller acceptance rate "
            f"collapse to {acceptance_str} — down roughly 12 percentage points from prior-week levels. "
            f"At current offer volume, this misalignment is costing approximately {missed_closes} "
            f"accepted offers per week and eroding acquisition margins to {acq_margin_str}."
        ),
        "root_causes": [
            (
                f"AVM drift: The automated valuation model appears to have overestimated "
                f"{issue.market} {issue.segment.replace('_', ' ')} home values by {offer_pct_str}, "
                f"likely due to stale comparable sales data or a segment-specific demand shift "
                f"not yet reflected in the model inputs."
            ),
            (
                f"Feedback loop lag: Opendoor's pricing model typically recalibrates on a weekly "
                f"cycle, meaning 1-2 weeks of above-market offers are generated before the signal "
                f"appears in acceptance rate data. The {issue.market} mid_tier segment shows "
                f"exactly this pattern — misalignment began before the acceptance rate drop."
            ),
            (
                f"Segment-specific exposure: Entry_level and premium segments in {issue.market} "
                f"appear unaffected, suggesting the AVM error is concentrated in the mid_tier "
                f"comparable set, possibly driven by outlier comps in one or two zip codes."
            ),
        ],
        "business_impact": (
            f"At {offer_count} offers/week and a {offer_pct_str} above-market offer position, "
            f"Opendoor is overpaying on each acquired home. With acquisition margin compressed to "
            f"{acq_margin_str}, the buffer against holding costs (~1.5%), transaction fees (~1%), "
            f"and repair contingencies (~0.5-1%) is effectively eliminated. "
            f"Homes acquired this week at these margins will likely generate realized losses at resale "
            f"unless {issue.market} values appreciate materially in the next 60-90 day hold period. "
            f"Additionally, the {acceptance_str} acceptance rate — if persistent — will reduce "
            f"{issue.market} mid_tier volume by an estimated {missed_closes} transactions/week."
        ),
        "recommended_actions": [
            (
                f"Pricing team: Pull all {issue.market} {issue.segment.replace('_', ' ')} "
                f"comparable sales from the past 30 days and audit the AVM inputs by zip code. "
                f"Apply a manual -3% offer adjustment across the segment by EOD tomorrow while "
                f"the model recalibration is completed."
            ),
            (
                f"Analytics team: Set a real-time alert threshold so that any market/segment "
                f"combination where avg_offer_vs_market_pct exceeds +2% for 3 consecutive days "
                f"triggers an automated Slack notification to the Pricing Lead. "
                f"Implement by end of this sprint."
            ),
            (
                f"Operations team: Place a temporary hold on {issue.market} {issue.segment.replace('_', ' ')} "
                f"acquisitions above $450K list price until the AVM recalibration is validated — "
                f"this caps the margin exposure while preserving volume on the lower end of the segment. "
                f"Review hold in 72 hours."
            ),
        ],
        "confidence": issue.confidence,
        "owner": "pricing",
        "mode": "mock",
    }


def _mock_inventory_aging(issue: Issue) -> dict:
    """High-quality mock for inventory aging issues."""
    snap = issue.metrics_snapshot
    aging_rate = snap.get("aging_inventory_rate", "N/A")
    avg_dom = snap.get("avg_days_on_market", "N/A")
    inv_count = snap.get("inventory_count", 0)
    resale_margin = snap.get("avg_resale_margin", "N/A")

    def pct(v):
        if v == "N/A" or v is None:
            return "N/A"
        return f"{float(v) * 100:.1f}%"

    aging_pct = pct(aging_rate)
    resale_pct = pct(resale_margin)
    aged_homes = int(float(inv_count) * float(aging_rate)) if (inv_count and aging_rate != "N/A") else 0

    return {
        "executive_summary": (
            f"{issue.market} {issue.segment.replace('_', ' ')} inventory is aging materially, "
            f"with {aging_pct} of active listings ({aged_homes} homes) exceeding 90 days on market "
            f"and average DOM now at {avg_dom} days. "
            f"The trend has been worsening for multiple consecutive weeks, indicating a structural "
            f"demand-supply imbalance rather than a temporary seasonal blip. "
            f"Without intervention, these homes will require markdown pricing to clear, "
            f"compressing resale margins from current {resale_pct}."
        ),
        "root_causes": [
            (
                f"Resale pricing too aggressive: Homes listed above the market's current "
                f"buyer demand level in {issue.market} are not moving at list price. "
                f"The progressive DOM increase over 6+ weeks suggests initial listing prices "
                f"were set based on acquisition comps rather than current resale demand."
            ),
            (
                f"Demand softening in {issue.market}: Broader market conditions may have "
                f"weakened since acquisition — rising mortgage rates, seasonal slowdown, "
                f"or increased competing inventory. The {issue.segment.replace('_', ' ')} segment "
                f"appears most exposed, possibly due to buyer affordability constraints at this price tier."
            ),
            (
                f"Insufficient markdown cadence: Opendoor's standard markdown trigger "
                f"(typically at 30/60/90 days) may not be responding fast enough to the "
                f"{issue.market} market velocity, allowing homes to accumulate in the "
                f"90+ day bucket faster than they are cleared."
            ),
        ],
        "business_impact": (
            f"With {aged_homes} homes in the 90+ day bucket at {aging_pct} of inventory, "
            f"Opendoor faces a choice between markdown pricing (estimated 3-8% reduction to clear) "
            f"or continued carrying costs (~$1,200-2,500/month/home for {issue.market}). "
            f"At current resale margins of {resale_pct}, a 5% markdown would eliminate the "
            f"margin entirely on aging homes. "
            f"Capital tied up in aged inventory also reduces Opendoor's capacity to acquire "
            f"new homes in more favorable segments."
        ),
        "recommended_actions": [
            (
                f"Market-ops team: Implement an immediate 3% price reduction on all "
                f"{issue.market} {issue.segment.replace('_', ' ')} listings exceeding 75 days DOM. "
                f"For homes over 100 days, apply a 5% reduction. "
                f"Execute price changes by end of business Friday."
            ),
            (
                f"Pricing team: Review acquisition offers in {issue.market} {issue.segment.replace('_', ' ')} "
                f"for the past 8 weeks and identify if any AVM segments or zip codes show systematic "
                f"overvaluation at resale. Pause new acquisitions in zip codes with 3+ aged homes "
                f"until the resale velocity audit is complete."
            ),
            (
                f"Analytics team: Add a leading indicator dashboard tracking {issue.market} buyer "
                f"demand signals (showings per listing, offer receipt rate) to provide earlier warning "
                f"of demand softening. Target: 2-week lead time before DOM breach. "
                f"Present dashboard to market-ops lead by next Monday."
            ),
        ],
        "confidence": issue.confidence,
        "owner": "market-ops",
        "mode": "mock",
    }


def _mock_funnel_deterioration(issue: Issue) -> dict:
    """High-quality mock for funnel deterioration issues."""
    snap = issue.metrics_snapshot
    l2o = snap.get("lead_to_offer_rate", "N/A")
    o2c = snap.get("offer_to_close_rate", "N/A")
    leads = snap.get("lead_count", 0)
    closes = snap.get("close_count", 0)
    funnel_eff = snap.get("funnel_efficiency", "N/A")

    def pct(v):
        if v == "N/A" or v is None:
            return "N/A"
        return f"{float(v) * 100:.1f}%"

    l2o_pct = pct(l2o)
    o2c_pct = pct(o2c)
    funnel_pct = pct(funnel_eff)

    # Estimate impact
    baseline_l2o = 0.58
    current_l2o = float(l2o) if l2o != "N/A" else 0.40
    lost_offers = int(leads * (baseline_l2o - current_l2o)) if leads else 0

    return {
        "executive_summary": (
            f"{issue.market} {issue.segment.replace('_', ' ')} is showing a deteriorating "
            f"seller conversion funnel: lead-to-offer rate has fallen to {l2o_pct} "
            f"(down ~3% WoW for multiple consecutive weeks), reducing overall funnel efficiency "
            f"to {funnel_pct}. "
            f"At {leads} leads this week, the degraded conversion rate translates to approximately "
            f"{lost_offers} fewer offers generated versus the historical baseline — a volume shortfall "
            f"that will flow through to close counts in 2-3 weeks if not addressed."
        ),
        "root_causes": [
            (
                f"Product/experience friction: A declining lead-to-offer rate without a "
                f"corresponding lead volume decline typically indicates friction in the offer "
                f"generation flow — slower offer turnaround time, UI issues in the offer "
                f"presentation, or sellers dropping off during the inspection/terms review step."
            ),
            (
                f"Offer competitiveness gap: If {issue.market} sellers are receiving competing "
                f"offers from traditional buyers or other iBuyers, Opendoor's offer may no longer "
                f"be compelling enough to hold sellers through the acceptance flow. "
                f"This would manifest as the exact pattern seen: leads arrive but don't convert."
            ),
            (
                f"Operational capacity constraint: If Opendoor's {issue.market} underwriting "
                f"or offer team is backlogged, offer generation SLAs may be slipping — sellers "
                f"who don't receive an offer within their expected window abandon the process. "
                f"Worth validating median offer turnaround time for this market."
            ),
        ],
        "business_impact": (
            f"With lead-to-offer rate at {l2o_pct} and falling ~3% per week, {issue.market} "
            f"is on track to lose an additional 15-20% of offer volume over the next 4 weeks "
            f"if the trend continues at its current trajectory. "
            f"At {closes} closes this week, even a 10% close reduction represents "
            f"{int(closes * 0.10)} fewer transactions — each worth $8-15K in gross profit "
            f"at standard margins. "
            f"The funnel deterioration also increases customer acquisition cost per close, "
            f"since marketing spend is fixed while volume declines."
        ),
        "recommended_actions": [
            (
                f"Growth team: Pull the {issue.market} offer funnel drop-off report by step "
                f"(lead received → offer generated → offer viewed → offer accepted) for the "
                f"past 3 weeks and identify the specific step where fall-off increased. "
                f"Report findings to leadership by Wednesday."
            ),
            (
                f"Operations team: Audit {issue.market} offer turnaround SLA compliance for "
                f"the past 2 weeks. If median offer generation time exceeds 24 hours, escalate "
                f"to ops capacity planning and consider temporary underwriting surge support. "
                f"SLA audit to be completed by EOD tomorrow."
            ),
            (
                f"Pricing team: Compare {issue.market} {issue.segment.replace('_', ' ')} "
                f"Opendoor offers against Zillow/Offerpad comparable offers for the same homes "
                f"(use the 10 most recent rejections). If Opendoor is systematically below "
                f"competitor offers by >2%, initiate a competitive adjustment review this week."
            ),
        ],
        "confidence": issue.confidence,
        "owner": "growth",
        "mode": "mock",
    }


def _mock_margin_compression(issue: Issue) -> dict:
    """High-quality mock for margin compression issues."""
    snap = issue.metrics_snapshot
    acq_margin = snap.get("avg_acquisition_margin", "N/A")
    resale_margin = snap.get("avg_resale_margin", "N/A")
    offer_vs_market = snap.get("avg_offer_vs_market_pct", "N/A")

    def pct(v):
        if v == "N/A" or v is None:
            return "N/A"
        return f"{float(v) * 100:.1f}%"

    return {
        "executive_summary": (
            f"{issue.market} {issue.segment.replace('_', ' ')} acquisition margins have compressed "
            f"to {pct(acq_margin)}, falling materially over the past week and approaching the "
            f"minimum viable threshold needed to cover operating costs. "
            f"With offer prices running {pct(offer_vs_market)} relative to market value, "
            f"the compression appears driven by AVM overvaluation rather than market deterioration, "
            f"making it addressable through model recalibration."
        ),
        "root_causes": [
            (
                f"Offer price drift: With avg_offer_vs_market_pct at {pct(offer_vs_market)}, "
                f"Opendoor is systematically acquiring homes above their market estimated value, "
                f"directly reducing the spread available as acquisition margin."
            ),
            (
                f"Cost structure erosion: At {pct(acq_margin)} acquisition margin, "
                f"the buffer for holding costs (est. 1.5%), transaction costs (~1%), "
                f"and repair/improvement spend (~0.5-2%) is insufficient. "
                f"This signals that the pricing model is not adequately accounting for "
                f"total cost of ownership in this market/segment."
            ),
        ],
        "business_impact": (
            f"Homes acquired in {issue.market} {issue.segment.replace('_', ' ')} at "
            f"{pct(acq_margin)} acquisition margin carry a high probability of generating "
            f"realized losses at resale after all costs. "
            f"Given Opendoor's typical 60-90 day hold period, homes acquired this week "
            f"will hit the resale market in Q2 — meaning today's recalibration prevents "
            f"Q2 margin compression at scale. "
            f"Current resale margin of {pct(resale_margin)} provides a partial buffer "
            f"but does not offset the acquisition-side overpayment if market values soften."
        ),
        "recommended_actions": [
            (
                f"Pricing team: Apply an immediate -2% offer adjustment to all new "
                f"{issue.market} {issue.segment.replace('_', ' ')} acquisitions while the "
                f"AVM recalibration is completed. This will temporarily reduce acceptance rates "
                f"but is preferable to continued below-threshold margin acquisition. "
                f"Implement by tomorrow's offer batch."
            ),
            (
                f"Finance team: Flag all {issue.market} {issue.segment.replace('_', ' ')} "
                f"homes acquired in the past 3 weeks for enhanced margin monitoring. "
                f"If resale margin at close falls below 2%, trigger a post-mortem review "
                f"of the AVM inputs used at acquisition time."
            ),
            (
                f"Analytics team: Build a real-time margin health dashboard segmented by "
                f"market/segment/zip showing acquisition margin trend over rolling 4 weeks. "
                f"Set automated alerts when any cell falls below 2.5% for 2 consecutive weeks. "
                f"Deploy to the Pricing team Slack channel by end of this sprint."
            ),
        ],
        "confidence": issue.confidence,
        "owner": "pricing",
        "mode": "mock",
    }


def _get_mock_response(issue: Issue) -> dict:
    """Route to the appropriate mock response based on issue type."""
    mock_map = {
        "PRICING_MISALIGNMENT": _mock_pricing_misalignment,
        "INVENTORY_AGING": _mock_inventory_aging,
        "FUNNEL_DETERIORATION": _mock_funnel_deterioration,
        "MARGIN_COMPRESSION": _mock_margin_compression,
    }
    mock_fn = mock_map.get(issue.issue_type)
    if mock_fn:
        return mock_fn(issue)

    # Generic fallback (should not be needed)
    return {
        "executive_summary": f"Issue detected: {issue.title}. Review evidence for details.",
        "root_causes": [e for e in issue.evidence[:2]],
        "business_impact": "Impact requires further analysis.",
        "recommended_actions": ["Review issue evidence with team lead.", "Investigate root cause.", "Monitor next week."],
        "confidence": issue.confidence,
        "owner": issue.owner,
        "mode": "mock",
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_issue(issue: Issue, use_mock: bool = False) -> dict:
    """
    Send a detected issue to Claude for structured reasoning and action generation.

    Args:
        issue:    Issue object from detection/rules.py
        use_mock: If True, use pre-written mock response instead of calling API.
                  Auto-set to True if ANTHROPIC_API_KEY is not available.

    Returns:
        dict with keys:
          executive_summary, root_causes (list), business_impact,
          recommended_actions (list), confidence, owner, mode ("live"|"mock")
    """
    # Auto-fallback to mock if no API key
    if not use_mock and not os.environ.get("ANTHROPIC_API_KEY"):
        use_mock = True

    if use_mock:
        return _get_mock_response(issue)

    # Live API call
    user_prompt = build_issue_reasoning_prompt(issue)
    try:
        result = _call_claude(SYSTEM_PROMPT, user_prompt)
        result["mode"] = "live"
        return result
    except Exception as e:
        print(f"  [WARNING] Claude API call failed for {issue.issue_id}: {e}")
        print(f"  [WARNING] Falling back to mock response.")
        result = _get_mock_response(issue)
        result["mode"] = "mock_fallback"
        return result


def analyze_all_issues(issues: list, use_mock: bool = False) -> list[dict]:
    """
    Analyze a list of Issue objects, returning one analysis dict per issue.

    Respects use_mock flag; auto-detects API key availability.

    Args:
        issues:   List of Issue objects
        use_mock: Force mock mode for all analyses

    Returns:
        List of analysis dicts in the same order as input issues.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        use_mock = True

    analyses = []
    for issue in issues:
        analysis = analyze_issue(issue, use_mock=use_mock)
        analyses.append(analysis)

    return analyses
