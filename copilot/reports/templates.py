"""
reports/templates.py
--------------------
Templates for all report output formats produced by the Opendoor Pricing &
Conversion Copilot.

Output formats:
  1. Executive Markdown Report — full briefing document for leadership review
  2. JSON Alerts — machine-readable alert list for downstream systems
  3. Action Summaries — short Slack/email notifications per issue

Template design:
  - Pure Python f-strings (no external template engine dependency)
  - All templates receive structured dicts, not raw Issue objects
  - Formatting helpers ensure consistent number presentation
"""

from datetime import datetime
from typing import Any


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _pct(v: Any, decimals: int = 1) -> str:
    """Format a float as a percentage string."""
    if v is None:
        return "N/A"
    try:
        return f"{float(v) * 100:.{decimals}f}%"
    except (TypeError, ValueError):
        return str(v)


def _pp(v: Any) -> str:
    """Format a float delta as signed percentage points."""
    if v is None:
        return "N/A"
    try:
        val = float(v) * 100
        sign = "+" if val >= 0 else ""
        return f"{sign}{val:.1f}pp"
    except (TypeError, ValueError):
        return str(v)


def _days(v: Any) -> str:
    """Format a days value."""
    if v is None:
        return "N/A"
    try:
        sign = "+" if float(v) >= 0 else ""
        return f"{sign}{float(v):.1f}d"
    except (TypeError, ValueError):
        return str(v)


def _severity_emoji(severity: str) -> str:
    """Map severity to a text indicator for markdown."""
    return {
        "critical": "CRITICAL",
        "high":     "HIGH    ",
        "medium":   "MEDIUM  ",
        "low":      "LOW     ",
    }.get(severity, severity.upper())


def _severity_badge(severity: str) -> str:
    """Markdown badge-style severity indicator."""
    badges = {
        "critical": "[CRITICAL]",
        "high":     "[HIGH]",
        "medium":   "[MEDIUM]",
        "low":      "[LOW]",
    }
    return badges.get(severity, severity.upper())


# ---------------------------------------------------------------------------
# Executive Markdown Report templates
# ---------------------------------------------------------------------------

REPORT_HEADER_TEMPLATE = """\
# Opendoor Pricing & Conversion Copilot
## Weekly Business Intelligence Report

**Generated:** {generated_at}
**Data through:** Week ending {week_end}
**Markets monitored:** {markets}
**Issues detected:** {issue_count} ({critical_count} critical, {high_count} high, {medium_count} medium)

---
"""

EXECUTIVE_OVERVIEW_TEMPLATE = """\
## 1. Executive Overview

{overview_text}

---
"""

PRIORITY_ISSUES_HEADER = """\
## 2. Priority Issues (Ranked by Severity)

"""

ISSUE_SECTION_TEMPLATE = """\
### {rank}. {severity_badge} {title}

**Market:** {market} | **Segment:** {segment} | **Owner:** {owner} | **Confidence:** {confidence}

#### Summary
{executive_summary}

#### Evidence
{evidence_bullets}

#### Root Causes
{root_cause_bullets}

#### Business Impact
{business_impact}

#### Recommended Actions
{action_bullets}

---
"""

MARKET_FINDINGS_HEADER = """\
## 3. Market-by-Market Findings

"""

MARKET_SUMMARY_TEMPLATE = """\
### {market}

| Segment | Offer Acceptance | Lead-to-Offer | Avg DOM | Acq Margin | Status |
|---------|-----------------|------------|---------|------------|--------|
{rows}

"""

ACTIONS_TABLE_TEMPLATE = """\
## 4. Recommended Actions Summary

| Priority | Issue | Market | Owner | Action | Timeframe |
|----------|-------|--------|-------|--------|-----------|
{rows}

---
"""

APPENDIX_TEMPLATE = """\
## 5. Appendix: Supporting Metrics

### Metric Definitions Used in This Report

| Metric | Formula | Warn Threshold | Critical Threshold |
|--------|---------|----------------|-------------------|
| Offer Acceptance Rate | accepted_offers / offers_made | WoW drop > 5% | WoW drop > 10% |
| Lead-to-Offer Rate | offers_made / leads | WoW drop > 3% | WoW drop > 6% |
| Offer-to-Close Rate | closes / accepted_offers | WoW drop > 4% | WoW drop > 8% |
| Avg Offer vs Market % | (offer_price - market_value) / market_value | > +2% | > +4% |
| Aging Inventory Rate | homes > 90 DOM / total inventory | > 15% | > 20% |
| Avg Days on Market | mean(days_on_market) | WoW +5 days | WoW +10 days |
| Avg Acquisition Margin | mean(acq_margin_estimate) | WoW -1pp | WoW -2pp |

### Detection Rules Applied
- **Pricing Misalignment**: Offer > +2% above market AND acceptance rate WoW drop > 5%
- **Inventory Aging**: Aging rate > 15% OR DOM increasing 5+ days for 2+ consecutive weeks
- **Funnel Deterioration**: Lead-to-offer WoW drop > 3% OR offer-to-close WoW drop > 4%
- **Margin Compression**: Acquisition margin WoW drop > 2pp OR absolute margin < 2%

### Data Notes
- Synthetic data covers 12 weeks across Phoenix, Atlanta, Dallas, Miami
- Each market/segment/zip combination produces one row per week
- Aging inventory rate estimated via log-normal DOM distribution model
- All WoW deltas computed within market-segment groups

---
*Report generated by Opendoor Pricing & Conversion Copilot*
"""


# ---------------------------------------------------------------------------
# JSON Alert template
# ---------------------------------------------------------------------------

def build_json_alert(issue_dict: dict, analysis: dict, rank: int) -> dict:
    """
    Build a single machine-readable JSON alert from an issue and its analysis.

    Suitable for ingestion by Slack bots, PagerDuty, Jira automation, etc.
    """
    return {
        "alert_id": issue_dict["issue_id"],
        "rank": rank,
        "severity": issue_dict["severity"],
        "issue_type": issue_dict["issue_type"],
        "title": issue_dict["title"],
        "market": issue_dict["market"],
        "segment": issue_dict["segment"],
        "week_start": issue_dict["week_start"],
        "owner": analysis.get("owner", issue_dict.get("owner", "")),
        "confidence": analysis.get("confidence", issue_dict.get("confidence", "")),
        "executive_summary": analysis.get("executive_summary", ""),
        "recommended_actions": analysis.get("recommended_actions", []),
        "key_metrics": issue_dict.get("metrics_snapshot", {}),
        "wow_deltas": issue_dict.get("wow_deltas", {}),
        "analysis_mode": analysis.get("mode", "unknown"),
    }


# ---------------------------------------------------------------------------
# Slack/Email action summary template
# ---------------------------------------------------------------------------

def build_action_summary(issue_dict: dict, analysis: dict) -> str:
    """
    Build a short Slack/email action summary for a single issue.

    Format: [SEVERITY] Title — 2-sentence summary — Primary action.
    """
    severity = issue_dict["severity"].upper()
    title = issue_dict["title"]
    market = issue_dict["market"]
    segment = issue_dict["segment"].replace("_", " ")
    owner = analysis.get("owner", issue_dict.get("owner", "unknown"))

    summary = analysis.get("executive_summary", "")
    # Truncate to first 2 sentences
    sentences = summary.split(". ")
    short_summary = ". ".join(sentences[:2]).strip()
    if not short_summary.endswith("."):
        short_summary += "."

    actions = analysis.get("recommended_actions", [])
    primary_action = actions[0] if actions else "Review issue details."

    return (
        f"[{severity}] {title}\n"
        f"{short_summary}\n"
        f"Action ({owner}): {primary_action}"
    )


# ---------------------------------------------------------------------------
# Market summary row formatter
# ---------------------------------------------------------------------------

def format_market_row(
    segment: str,
    metrics: dict,
    has_issue: bool,
) -> str:
    """
    Format a single row for the market-by-market findings table.
    """
    acceptance = _pct(metrics.get("offer_acceptance_rate"))
    l2o = _pct(metrics.get("lead_to_offer_rate"))
    dom = f"{metrics.get('avg_days_on_market', 'N/A'):.0f}d" if metrics.get("avg_days_on_market") else "N/A"
    margin = _pct(metrics.get("avg_acquisition_margin"))
    status = "Issue Detected" if has_issue else "Healthy"

    seg_label = segment.replace("_", " ").title()
    return f"| {seg_label} | {acceptance} | {l2o} | {dom} | {margin} | {status} |"
