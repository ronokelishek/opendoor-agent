"""
reports/build_report.py
-----------------------
Assembles all report output formats for the Opendoor Pricing & Conversion Copilot.

Functions:
  build_executive_report(issues, analyses, metrics_df)  → markdown string
  build_json_alerts(issues, analyses)                   → list of dicts
  build_action_summaries(issues, analyses)              → list of strings
  save_outputs(report_md, alerts_json, summaries)       → saves to output/
"""

import json
import os
from datetime import datetime
from typing import List

import pandas as pd

from detection.issue_types import Issue
from reports.templates import (
    REPORT_HEADER_TEMPLATE,
    EXECUTIVE_OVERVIEW_TEMPLATE,
    PRIORITY_ISSUES_HEADER,
    ISSUE_SECTION_TEMPLATE,
    MARKET_FINDINGS_HEADER,
    MARKET_SUMMARY_TEMPLATE,
    ACTIONS_TABLE_TEMPLATE,
    APPENDIX_TEMPLATE,
    build_json_alert,
    build_action_summary,
    format_market_row,
    _pct,
    _pp,
    _severity_badge,
)

# ---------------------------------------------------------------------------
# Output directory
# ---------------------------------------------------------------------------

def _output_dir() -> str:
    """Resolve the copilot/output/ directory path."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "..", "output")


# ---------------------------------------------------------------------------
# Executive Markdown Report
# ---------------------------------------------------------------------------

def build_executive_report(
    issues: List[Issue],
    analyses: List[dict],
    metrics_df: pd.DataFrame,
) -> str:
    """
    Build the full executive markdown report.

    Sections:
      1. Header + meta
      2. Executive Overview
      3. Priority Issues (ranked by severity)
      4. Market-by-Market Findings
      5. Recommended Actions Table
      6. Appendix: Supporting Metrics

    Args:
        issues:     List of Issue objects (sorted by severity)
        analyses:   List of analysis dicts from reasoning_agent (same order)
        metrics_df: DataFrame from compute_wow_changes(compute_weekly_metrics(...))

    Returns:
        Full markdown string.
    """
    sections = []

    # --- Header ---
    now = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    latest_week = metrics_df["week_start"].max()
    week_end_str = str(latest_week)[:10] if hasattr(latest_week, '__str__') else str(latest_week)
    markets = ", ".join(sorted(metrics_df["market"].unique()))

    severity_counts = {s: 0 for s in ["critical", "high", "medium", "low"]}
    for issue in issues:
        severity_counts[issue.severity] = severity_counts.get(issue.severity, 0) + 1

    header = REPORT_HEADER_TEMPLATE.format(
        generated_at=now,
        week_end=week_end_str,
        markets=markets,
        issue_count=len(issues),
        critical_count=severity_counts["critical"],
        high_count=severity_counts["high"],
        medium_count=severity_counts["medium"],
    )
    sections.append(header)

    # --- Executive Overview ---
    if issues:
        most_severe = issues[0]  # Already sorted by severity
        healthy_markets = _identify_healthy_markets(issues, metrics_df)

        overview = _build_overview_text(issues, analyses, most_severe, healthy_markets)
    else:
        overview = (
            "No issues detected this week. All monitored markets are operating within "
            "normal thresholds across pricing, inventory, funnel, and margin metrics."
        )

    sections.append(EXECUTIVE_OVERVIEW_TEMPLATE.format(overview_text=overview))

    # --- Priority Issues ---
    sections.append(PRIORITY_ISSUES_HEADER)
    for rank, (issue, analysis) in enumerate(zip(issues, analyses), start=1):
        evidence_bullets = "\n".join(f"- {e}" for e in issue.evidence)
        root_cause_bullets = "\n".join(f"- {rc}" for rc in analysis.get("root_causes", []))
        action_bullets = "\n".join(
            f"{i+1}. {a}" for i, a in enumerate(analysis.get("recommended_actions", []))
        )

        section = ISSUE_SECTION_TEMPLATE.format(
            rank=rank,
            severity_badge=_severity_badge(issue.severity),
            title=issue.title,
            market=issue.market,
            segment=issue.segment.replace("_", " ").title(),
            owner=analysis.get("owner", issue.owner),
            confidence=analysis.get("confidence", issue.confidence),
            executive_summary=analysis.get("executive_summary", "No summary available."),
            evidence_bullets=evidence_bullets,
            root_cause_bullets=root_cause_bullets if root_cause_bullets else "- See evidence above.",
            business_impact=analysis.get("business_impact", "Impact not quantified."),
            action_bullets=action_bullets if action_bullets else "1. Review with team lead.",
        )
        sections.append(section)

    # --- Market-by-Market Findings ---
    sections.append(MARKET_FINDINGS_HEADER)
    issue_keys = {(i.market, i.segment) for i in issues}

    for market in sorted(metrics_df["market"].unique()):
        latest_week_val = metrics_df["week_start"].max()
        market_latest = metrics_df[
            (metrics_df["market"] == market) &
            (metrics_df["week_start"] == latest_week_val)
        ]

        rows = []
        for segment in ["entry_level", "mid_tier", "premium"]:
            seg_data = market_latest[market_latest["home_segment"] == segment]
            if seg_data.empty:
                continue
            row_data = seg_data.iloc[0].to_dict()
            has_issue = (market, segment) in issue_keys
            rows.append(format_market_row(segment, row_data, has_issue))

        rows_str = "\n".join(rows) if rows else "| No data | — | — | — | — | — |"
        sections.append(MARKET_SUMMARY_TEMPLATE.format(
            market=market,
            rows=rows_str,
        ))

    # --- Actions Table ---
    sections.append(_build_actions_table(issues, analyses))

    # --- Appendix ---
    sections.append(APPENDIX_TEMPLATE)

    return "\n".join(sections)


def _build_overview_text(
    issues: List[Issue],
    analyses: List[dict],
    most_severe: Issue,
    healthy_markets: List[str],
) -> str:
    """Construct the executive overview paragraph."""
    critical_issues = [i for i in issues if i.severity == "critical"]
    high_issues = [i for i in issues if i.severity == "high"]
    medium_issues = [i for i in issues if i.severity == "medium"]

    severity_desc = []
    if critical_issues:
        severity_desc.append(f"{len(critical_issues)} critical")
    if high_issues:
        severity_desc.append(f"{len(high_issues)} high")
    if medium_issues:
        severity_desc.append(f"{len(medium_issues)} medium")

    severity_str = ", ".join(severity_desc) if severity_desc else "no high-severity"
    healthy_str = " and ".join(healthy_markets) if healthy_markets else "none identified"

    # Get primary action for top issue
    top_analysis = analyses[0] if analyses else {}
    top_actions = top_analysis.get("recommended_actions", [])
    top_action = top_actions[0][:120] if top_actions else "Review all detected issues."

    overview = (
        f"This week's scan detected {len(issues)} issues requiring attention "
        f"({severity_str} severity) across the monitored market portfolio. "
        f"The highest-priority concern is **{most_severe.title}** — "
        f"{top_analysis.get('executive_summary', '')[:200]}... "
        f"{healthy_str} {'market' if len(healthy_markets) == 1 else 'markets'} "
        f"{'is' if len(healthy_markets) == 1 else 'are'} operating within healthy parameters "
        f"and can serve as a performance baseline. "
        f"**Immediate leadership priority**: {top_action}"
    )
    return overview


def _identify_healthy_markets(issues: List[Issue], metrics_df: pd.DataFrame) -> List[str]:
    """Return list of markets with no detected issues."""
    all_markets = set(metrics_df["market"].unique())
    affected_markets = {i.market for i in issues}
    return sorted(all_markets - affected_markets)


def _build_actions_table(issues: List[Issue], analyses: List[dict]) -> str:
    """Build the recommended actions summary table."""
    rows = []
    priority = 1
    for issue, analysis in zip(issues, analyses):
        actions = analysis.get("recommended_actions", [])
        owner = analysis.get("owner", issue.owner)
        for action in actions[:1]:  # Top action per issue in summary table
            # Extract timeframe hint from action text
            timeframe = "This week"
            for hint in ["by EOD", "by end", "by tomorrow", "by Monday", "by Wednesday", "by Friday", "this sprint"]:
                if hint.lower() in action.lower():
                    idx = action.lower().find(hint.lower())
                    timeframe = action[idx:idx+20].split(".")[0].strip()
                    break

            short_action = action[:80] + "..." if len(action) > 80 else action
            rows.append(
                f"| {priority} | {issue.issue_type.replace('_', ' ').title()} | "
                f"{issue.market} | {owner} | {short_action} | {timeframe} |"
            )
            priority += 1

    rows_str = "\n".join(rows) if rows else "| — | No actions required | — | — | — | — |"
    return ACTIONS_TABLE_TEMPLATE.format(rows=rows_str)


# ---------------------------------------------------------------------------
# JSON Alerts
# ---------------------------------------------------------------------------

def build_json_alerts(issues: List[Issue], analyses: List[dict]) -> List[dict]:
    """
    Build a machine-readable JSON alert list.

    Returns one alert dict per issue, ranked by severity.
    Suitable for Slack bots, PagerDuty, Jira integrations, etc.
    """
    alerts = []
    for rank, (issue, analysis) in enumerate(zip(issues, analyses), start=1):
        alert = build_json_alert(issue.to_dict(), analysis, rank)
        alerts.append(alert)
    return alerts


# ---------------------------------------------------------------------------
# Action Summaries (Slack / email)
# ---------------------------------------------------------------------------

def build_action_summaries(issues: List[Issue], analyses: List[dict]) -> List[str]:
    """
    Build short Slack/email summaries for each detected issue.

    Format per summary:
      [SEVERITY] Issue Title
      2-sentence executive summary.
      Action (owner): Primary recommended action.
    """
    summaries = []
    for issue, analysis in zip(issues, analyses):
        summary = build_action_summary(issue.to_dict(), analysis)
        summaries.append(summary)
    return summaries


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def save_outputs(
    report_md: str,
    alerts_json: List[dict],
    summaries: List[str],
) -> dict:
    """
    Save all report outputs to copilot/output/.

    Files written:
      weekly_report.md       — Full executive markdown report
      alerts.json            — Machine-readable JSON alerts
      action_summaries.txt   — Slack/email action summaries

    Returns:
        dict mapping output type to file path.
    """
    output_dir = _output_dir()
    os.makedirs(output_dir, exist_ok=True)

    paths = {}

    # Markdown report
    report_path = os.path.join(output_dir, "weekly_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_md)
    paths["report"] = report_path

    # JSON alerts
    alerts_path = os.path.join(output_dir, "alerts.json")
    with open(alerts_path, "w", encoding="utf-8") as f:
        json.dump(alerts_json, f, indent=2, default=str)
    paths["alerts"] = alerts_path

    # Action summaries
    summaries_path = os.path.join(output_dir, "action_summaries.txt")
    with open(summaries_path, "w", encoding="utf-8") as f:
        f.write(f"Opendoor Copilot — Action Summaries\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}\n")
        f.write("=" * 60 + "\n\n")
        for i, summary in enumerate(summaries, start=1):
            f.write(f"Issue {i}:\n{summary}\n\n{'—' * 40}\n\n")
    paths["summaries"] = summaries_path

    return paths
