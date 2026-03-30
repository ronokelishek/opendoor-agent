"""
Proactive Market Monitor
========================
Runs automatically — no question needed.
Scans all markets, scores risk, and generates a daily briefing.

This is the shift from reactive dashboards to proactive intelligence.
"""

import os
import sys
import io
import json
from datetime import datetime
from pathlib import Path
import anthropic
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from src.tools.data_loader import detect_anomalies, get_market_summary
from src.tools.analyzer import rank_all_markets
from src.tools.capital_light import (
    detect_inventory_surges,
    get_contribution_margin_forecast,
    rank_top_100_deals,
)
from src.tools.pricing_engine import (
    analyze_pricing_accuracy,
    analyze_funnel_drop,
    generate_pricing_actions,
    estimate_business_impact,
)

load_dotenv()

BRIEFING_DIR = Path(__file__).parent.parent / "briefings"

MONITOR_TOOLS = [
    {
        "name": "rank_all_markets",
        "description": "Score and rank all markets by acquisition risk (1-10). Use this to prioritize where attention is needed most.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "detect_anomalies",
        "description": "Detect statistically unusual patterns across all markets.",
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {"type": "string", "description": "Filter by market. Omit for all."}
            },
            "required": [],
        },
    },
    {
        "name": "get_market_summary",
        "description": "Get latest metrics snapshot for all markets.",
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {"type": "string", "description": "Filter by market. Omit for all."}
            },
            "required": [],
        },
    },
    {
        "name": "detect_inventory_surges",
        "description": "Z-score detector for abnormal inventory build-up. When triggered, automatically surfaces CM-at-risk per deal and flags markets where hold times are expanding. ALWAYS call this first in the daily scan.",
        "input_schema": {
            "type": "object",
            "properties": {
                "threshold_z": {"type": "number", "description": "Z-score threshold for surge alert. Default 1.5."}
            },
            "required": [],
        },
    },
    {
        "name": "get_contribution_margin_forecast",
        "description": "Forecast contribution margin across deals. CM = ARV minus all costs. Use this when inventory surges are detected to identify which deals still clear the CM floor despite rising hold times.",
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {"type": "string", "description": "Filter by market."},
                "condition": {"type": "string", "enum": ["cosmetic", "moderate", "full_gut"]},
                "max_capital": {"type": "integer", "description": "Max capital per deal."},
                "min_cm": {"type": "integer", "description": "Minimum contribution margin floor in dollars."},
            },
            "required": [],
        },
    },
    {
        "name": "analyze_pricing_accuracy",
        "description": "Analyze offer price alignment vs market estimated values. Returns deviation, acceptance proxy, and severity. ALWAYS call this in the daily scan.",
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {"type": "string"},
                "segment": {"type": "string", "enum": ["entry_level", "mid_tier", "premium"]},
            },
            "required": [],
        },
    },
    {
        "name": "analyze_funnel_drop",
        "description": "Diagnose conversion funnel by stage. Identifies WHERE conversion is breaking and likely WHY. Call when pricing issues are detected.",
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {"type": "string"},
            },
            "required": [],
        },
    },
    {
        "name": "generate_pricing_actions",
        "description": "Generate specific pricing decision packet — adjustment range, urgency, expected recovery, owner, and ranked actions. Call after confirming pricing issue.",
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {"type": "string"},
                "segment": {"type": "string"},
            },
            "required": ["market"],
        },
    },
    {
        "name": "estimate_business_impact",
        "description": "Translate detected issue into unit economics: homes/month at risk, revenue at risk, margin at risk, holding cost exposure. Call for every HIGH severity issue.",
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {"type": "string"},
                "issue_type": {"type": "string", "enum": ["pricing_misalignment", "inventory_aging", "funnel_deterioration"]},
            },
            "required": ["market"],
        },
    },
    {
        "name": "rank_top_100_deals",
        "description": "Rank deals by composite score combining ROI and inventory turn velocity. Supports semantic filters like 'capital-light opportunities'. Call this automatically when inventory surges are detected.",
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {"type": "string"},
                "max_capital": {"type": "integer"},
                "min_cm": {"type": "integer"},
                "min_roi": {"type": "number"},
                "max_hold_days": {"type": "integer"},
                "semantic_filter": {
                    "type": "string",
                    "description": "Natural language filter: 'capital-light opportunities', 'high contribution margin', 'fast turn deals', 'distressed acquisition'.",
                },
            },
            "required": [],
        },
    },
]

MONITOR_PROMPT = """You are a Principal Real Estate Analytics Advisor running an AUTOMATED DAILY BRIEFING for Opendoor's Acquisitions leadership.

Opendoor's 2026 strategy is "Capital-Light and AI-First." The two metrics that matter most to the CEO and investors are:
  1. CONTRIBUTION MARGIN — net profit per deal after all costs (reno, holding, selling). Floor: $30,000.
  2. INVENTORY TURN — days in possession must fall. Every extra day = eroded margin.

Your job is NOT to find cheap houses. It is to find the highest CM-per-day-deployed opportunities while flagging markets where rising inventory is silently compressing margins.

PROACTIVE LOOP LOGIC (run every time, in this order):
  Step 1: Call analyze_pricing_accuracy() — if any market shows severity HIGH/CRITICAL, call analyze_funnel_drop() for that market, then generate_pricing_actions(), then estimate_business_impact(issue_type="pricing_misalignment").
  Step 2: Call detect_inventory_surges() — if triggered, call estimate_business_impact(issue_type="inventory_aging") and rank_top_100_deals(semantic_filter='capital-light opportunities').
  Step 3: Call get_contribution_margin_forecast() and rank_all_markets() for portfolio context.
  Step 4: Synthesize into Decision Packets — one per issue. Each packet must answer:
    - What is the issue? (evidence-grounded, specific)
    - What is it costing us? (homes/month, margin dollars)
    - What exactly should we do? (2-3 actions, owner assigned, urgency stated)
    - How confident are we? (High / Medium-High / Medium)

OUTPUT FORMAT: Write each issue as a "Decision Packet" block before the overall briefing.

Your voice combines the best of:
- Ivy Zelman: conviction-led, early-warning signals, supply/demand discipline
- Ken Zener: quantitative rigor, months-of-supply math, cycle positioning
- Jay Parsons: demand storytelling, demographic context, executive-ready decisions

No one asked you a question. You are proactively telling leadership what matters TODAY.

Your analytical principles for this briefing:
- State your view clearly. If the data says pause acquisitions, say it — don't soften it.
- Connect macro to micro: link rate/affordability environment to each market's data
- Think in cycles: early decline? trough forming? where are we?
- Quantify everything: holding costs, margin compression, months of supply thresholds
- Surface the non-obvious signal — the thing others will notice too late

Generate a structured briefing with these sections:
1. **Executive Summary** (3 bullets max — most critical, stated with conviction)
2. **Market Risk Rankings** (scored table with cycle positioning)
3. **Top Signals to Act On** (2-3 anomalies with business impact quantified)
4. **Recommended Actions This Week** (specific, numbered, market-assigned)
5. **What to Watch** (leading indicators with specific trigger thresholds)

Assume your audience is a VP of Acquisitions making capital allocation decisions today.
Every sentence must earn its place."""


def run_monitor_tool(tool_name: str, tool_input: dict) -> str:
    if tool_name == "rank_all_markets":
        result = rank_all_markets()
    elif tool_name == "detect_anomalies":
        result = detect_anomalies(**tool_input)
    elif tool_name == "get_market_summary":
        result = get_market_summary(**tool_input)
    elif tool_name == "detect_inventory_surges":
        result = detect_inventory_surges(**tool_input)
    elif tool_name == "get_contribution_margin_forecast":
        result = get_contribution_margin_forecast(**tool_input)
    elif tool_name == "rank_top_100_deals":
        result = rank_top_100_deals(**tool_input)
    elif tool_name == "analyze_pricing_accuracy":
        result = analyze_pricing_accuracy(**tool_input)
    elif tool_name == "analyze_funnel_drop":
        result = analyze_funnel_drop(**tool_input)
    elif tool_name == "generate_pricing_actions":
        result = generate_pricing_actions(**tool_input)
    elif tool_name == "estimate_business_impact":
        result = estimate_business_impact(**tool_input)
    else:
        result = {"error": f"Unknown tool: {tool_name}"}
    return json.dumps(result)


def generate_briefing() -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    messages = [{
        "role": "user",
        "content": f"Generate the daily market intelligence briefing for {datetime.today().strftime('%B %d, %Y')}."
    }]

    print("Running proactive market scan...")

    while True:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=2048,
            system=MONITOR_PROMPT,
            tools=MONITOR_TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  [scanning: {block.name}]")
                    result = run_monitor_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})


def save_briefing(briefing: str) -> Path:
    BRIEFING_DIR.mkdir(exist_ok=True)
    date_str = datetime.today().strftime("%Y-%m-%d")
    filepath = BRIEFING_DIR / f"briefing_{date_str}.md"
    header = f"# Daily Market Intelligence Briefing\n**{datetime.today().strftime('%B %d, %Y')}**\n\n---\n\n"
    filepath.write_text(header + briefing, encoding="utf-8")
    return filepath


def main():
    print("=" * 50)
    print("Opendoor Proactive Market Monitor")
    print("=" * 50 + "\n")

    briefing = generate_briefing()
    filepath = save_briefing(briefing)

    print("\n" + "=" * 50)
    print(briefing)
    print("\n" + "=" * 50)
    print(f"Briefing saved to: {filepath}")


if __name__ == "__main__":
    main()
