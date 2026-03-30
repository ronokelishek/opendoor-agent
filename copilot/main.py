"""
main.py
-------
Entry point for the Opendoor Pricing & Conversion Copilot.

Orchestrates the full pipeline:
  1. Load synthetic market data
  2. Compute weekly metrics + WoW deltas
  3. Run deterministic issue detection
  4. Reason about each issue with Claude (or mock if no API key)
  5. Build executive report, JSON alerts, and action summaries
  6. Save all outputs to copilot/output/
  7. Print terminal summary

Usage:
  python main.py           # Auto-detects API key; uses mock if absent
  python main.py --mock    # Force mock mode (no API calls)
  python main.py --live    # Force live API mode (requires ANTHROPIC_API_KEY)
"""

import argparse
import io
import os
import sys
import time

# Reconfigure stdout to UTF-8 to handle non-ASCII characters in output text
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Ensure copilot/ is on the Python path when run from repo root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.synthetic_data import generate_data
from metrics.calculations import compute_weekly_metrics, compute_wow_changes
from detection.rules import detect_all_issues
from agents.reasoning_agent import analyze_all_issues
from reports.build_report import (
    build_executive_report,
    build_json_alerts,
    build_action_summaries,
    save_outputs,
)


# ---------------------------------------------------------------------------
# Terminal output helpers
# ---------------------------------------------------------------------------

def _print_header():
    print()
    print("=" * 65)
    print("  OPENDOOR PRICING & CONVERSION COPILOT")
    print("  Proactive Business Intelligence · Weekly Scan")
    print("=" * 65)
    print()


def _print_section(title: str):
    print(f"\n{'-' * 55}")
    print(f"  {title}")
    print(f"{'-' * 55}")


def _print_issue_summary(issues: list):
    """Print a compact issue summary table to the terminal."""
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_issues = sorted(issues, key=lambda i: severity_order.get(i.severity, 9))

    print(f"\n  {'#':<3} {'SEVERITY':<10} {'MARKET':<10} {'SEGMENT':<15} {'ISSUE TYPE':<25}")
    print(f"  {'-'*3} {'-'*10} {'-'*10} {'-'*15} {'-'*25}")
    for rank, issue in enumerate(sorted_issues, start=1):
        seg = issue.segment.replace("_", " ").title()
        issue_type = issue.issue_type.replace("_", " ").title()
        print(f"  {rank:<3} {issue.severity.upper():<10} {issue.market:<10} {seg:<15} {issue_type:<25}")


def _print_action_summaries(summaries: list):
    """Print action summaries to the terminal."""
    for i, summary in enumerate(summaries, start=1):
        lines = summary.split("\n")
        print(f"\n  [{i}] {lines[0]}")
        for line in lines[1:]:
            print(f"      {line}")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main(force_mock: bool = False, force_live: bool = False):
    _print_header()

    # --- API key detection ---
    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if force_live and not has_api_key:
        print("  ERROR: --live flag requires ANTHROPIC_API_KEY environment variable.")
        print("  Set it with: export ANTHROPIC_API_KEY='your-key'")
        sys.exit(1)

    use_mock = force_mock or (not force_live and not has_api_key)

    if use_mock:
        print("  Mode: MOCK (pre-written responses — no API calls)")
        if not force_mock:
            print("  Note: Set ANTHROPIC_API_KEY env var to enable live Claude analysis.")
    else:
        print("  Mode: LIVE (calling Claude claude-opus-4-6)")

    # -----------------------------------------------------------------------
    # Step 1: Load data
    # -----------------------------------------------------------------------
    _print_section("Step 1: Loading Synthetic Market Data")
    t0 = time.time()
    df = generate_data()
    markets = df["market"].nunique()
    weeks = df["week"].nunique()
    rows = len(df)
    print(f"  Loaded {rows} rows | {weeks} weeks | {markets} markets")
    print(f"  Markets: {', '.join(sorted(df['market'].unique()))}")
    print(f"  Date range: {df['week_start'].min().date()} to {df['week_start'].max().date()}")
    print(f"  ({time.time() - t0:.2f}s)")

    # -----------------------------------------------------------------------
    # Step 2: Compute metrics + WoW deltas
    # -----------------------------------------------------------------------
    _print_section("Step 2: Computing Weekly Metrics + WoW Deltas")
    t0 = time.time()
    metrics_df = compute_weekly_metrics(df)
    metrics_df = compute_wow_changes(metrics_df)
    print(f"  Computed {len(metrics_df.columns)} metric columns")
    print(f"  Metric rows: {len(metrics_df)} (weeks × markets × segments)")
    print(f"  ({time.time() - t0:.2f}s)")

    # -----------------------------------------------------------------------
    # Step 3: Detect issues
    # -----------------------------------------------------------------------
    _print_section("Step 3: Running Deterministic Issue Detection")
    t0 = time.time()
    issues = detect_all_issues(metrics_df)
    print(f"  Detected {len(issues)} issues")

    if issues:
        _print_issue_summary(issues)
    else:
        print("  All markets healthy — no thresholds breached.")
    print(f"\n  ({time.time() - t0:.2f}s)")

    # -----------------------------------------------------------------------
    # Step 4: Reason with LLM (or mock)
    # -----------------------------------------------------------------------
    _print_section("Step 4: Generating AI Analysis")
    t0 = time.time()
    if issues:
        print(f"  Analyzing {len(issues)} issues...")
        analyses = analyze_all_issues(issues, use_mock=use_mock)
        mode_label = analyses[0].get("mode", "unknown") if analyses else "none"
        print(f"  Analysis mode: {mode_label}")
        print(f"  Completed {len(analyses)} analyses")
    else:
        analyses = []
        print("  No issues to analyze.")
    print(f"  ({time.time() - t0:.2f}s)")

    # -----------------------------------------------------------------------
    # Step 5: Build reports
    # -----------------------------------------------------------------------
    _print_section("Step 5: Building Reports")
    t0 = time.time()

    report_md = build_executive_report(issues, analyses, metrics_df)
    alerts_json = build_json_alerts(issues, analyses)
    summaries = build_action_summaries(issues, analyses)

    print(f"  Executive report: {len(report_md):,} characters")
    print(f"  JSON alerts: {len(alerts_json)} alerts")
    print(f"  Action summaries: {len(summaries)}")
    print(f"  ({time.time() - t0:.2f}s)")

    # -----------------------------------------------------------------------
    # Step 6: Save outputs
    # -----------------------------------------------------------------------
    _print_section("Step 6: Saving Outputs")
    t0 = time.time()
    paths = save_outputs(report_md, alerts_json, summaries)
    for output_type, path in paths.items():
        print(f"  {output_type:<12} -> {path}")
    print(f"  ({time.time() - t0:.2f}s)")

    # -----------------------------------------------------------------------
    # Step 7: Terminal summary
    # -----------------------------------------------------------------------
    _print_section("Summary")
    critical = sum(1 for i in issues if i.severity == "critical")
    high = sum(1 for i in issues if i.severity == "high")
    medium = sum(1 for i in issues if i.severity == "medium")

    print(f"\n  Total issues detected: {len(issues)}")
    print(f"    Critical : {critical}")
    print(f"    High     : {high}")
    print(f"    Medium   : {medium}")

    if summaries:
        print(f"\n  Top Priority Actions:")
        _print_action_summaries(summaries[:3])

    print(f"\n  Reports saved to: {paths.get('report', 'N/A')}")
    print()
    print("=" * 65)
    print("  Scan complete.")
    print("=" * 65)
    print()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Opendoor Pricing & Conversion Copilot — Weekly Business Scan"
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--mock",
        action="store_true",
        help="Force mock mode (use pre-written responses, no API calls)",
    )
    mode_group.add_argument(
        "--live",
        action="store_true",
        help="Force live mode (requires ANTHROPIC_API_KEY env var)",
    )
    args = parser.parse_args()

    main(force_mock=args.mock, force_live=args.live)
