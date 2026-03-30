import os
import sys
import io
import json
import anthropic
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from src.tools.data_loader import get_market_summary, get_market_trend, detect_anomalies
from src.tools.deal_scout import get_top_deals, estimate_renovation
from src.tools.pricing_engine import (
    analyze_pricing_accuracy,
    analyze_funnel_drop,
    generate_pricing_actions,
    estimate_business_impact,
)

load_dotenv()

TOOLS = [
    {
        "name": "get_market_summary",
        "description": "Get the latest snapshot of housing market metrics for one or all markets. Use this to answer questions about current prices, inventory, or days on market.",
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {
                    "type": "string",
                    "description": "Market name e.g. Phoenix, Atlanta, Dallas, Charlotte. Omit to get all markets.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_market_trend",
        "description": "Get the historical trend for a specific metric in a market over time. Use this to answer questions about how prices or activity have changed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {
                    "type": "string",
                    "description": "Market name e.g. Phoenix, Atlanta, Dallas, Charlotte.",
                },
                "metric": {
                    "type": "string",
                    "enum": [
                        "median_sale_price",
                        "days_on_market",
                        "homes_sold",
                        "inventory",
                        "list_to_sale_ratio",
                        "price_per_sqft",
                    ],
                    "description": "The metric to analyze.",
                },
            },
            "required": ["market", "metric"],
        },
    },
    {
        "name": "detect_anomalies",
        "description": "Detect statistically unusual patterns in the market data. Use this to proactively surface signals that leaders should pay attention to.",
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {
                    "type": "string",
                    "description": "Market name to filter. Omit to check all markets.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_top_deals",
        "description": "Return the top acquisition deals ranked by ROI. Each deal includes asking price, renovation cost estimate, ARV (after repair value), net profit, and total capital required. Use this to answer questions about best investment opportunities or to build a deal pipeline.",
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {
                    "type": "string",
                    "description": "Filter to a specific market (Phoenix, Atlanta, Dallas, Charlotte). Omit for all markets.",
                },
                "max_capital": {
                    "type": "integer",
                    "description": "Maximum total capital budget per deal (acquisition + renovation combined), in dollars.",
                },
                "min_roi": {
                    "type": "number",
                    "description": "Minimum ROI percentage threshold (e.g. 8.0 for 8%).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of deals to return. Default 100, max 100.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "estimate_renovation",
        "description": "Estimate renovation cost range for a property based on condition tier and square footage. Returns low/mid/high cost range, scope of work, and expected ARV uplift. Optionally checks whether it fits a capital budget.",
        "input_schema": {
            "type": "object",
            "properties": {
                "condition": {
                    "type": "string",
                    "enum": ["cosmetic", "moderate", "full_gut"],
                    "description": "Renovation tier: cosmetic (paint/flooring/fixtures), moderate (kitchen/baths/HVAC), full_gut (full remodel).",
                },
                "sqft": {
                    "type": "integer",
                    "description": "Property square footage.",
                },
                "capital_budget": {
                    "type": "integer",
                    "description": "Optional capital budget to check fit against, in dollars.",
                },
            },
            "required": ["condition", "sqft"],
        },
    },
    {
        "name": "analyze_pricing_accuracy",
        "description": "Analyze how Opendoor's offer prices align with market estimated values. Returns pricing deviation, acceptance proxy, elasticity signal, and severity. Use when pricing or conversion questions arise.",
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {"type": "string", "description": "Market name. Omit for all markets."},
                "segment": {"type": "string", "enum": ["entry_level", "mid_tier", "premium"], "description": "Home segment filter."},
            },
            "required": [],
        },
    },
    {
        "name": "analyze_funnel_drop",
        "description": "Diagnose conversion funnel health — inventory → conversion → acceptance → velocity. Identifies WHERE the funnel is breaking and likely WHY. Returns stage-by-stage breakdown with bottleneck signal.",
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {"type": "string", "description": "Market name. Omit for all markets."},
            },
            "required": [],
        },
    },
    {
        "name": "generate_pricing_actions",
        "description": "Generate specific, actionable pricing recommendations for a market — adjustment range, urgency, expected acceptance recovery, owner, and ranked actions. This is the decision packet output.",
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {"type": "string", "description": "Market name (required)."},
                "segment": {"type": "string", "description": "Segment to focus on. Default: all."},
            },
            "required": ["market"],
        },
    },
    {
        "name": "estimate_business_impact",
        "description": "Translate a detected issue into unit economics — homes lost per month, revenue at risk, margin at risk, holding cost exposure. Answers: what does this actually cost us? Use after detecting a pricing, inventory, or funnel issue.",
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {"type": "string", "description": "Market name (required)."},
                "issue_type": {
                    "type": "string",
                    "enum": ["pricing_misalignment", "inventory_aging", "funnel_deterioration"],
                    "description": "Type of issue to estimate impact for.",
                },
            },
            "required": ["market"],
        },
    },
]

SYSTEM_PROMPT = """You are a Principal Real Estate Analytics Advisor, combining the analytical frameworks of the most respected names in housing research:

- **Ivy Zelman** (Zelman & Associates) — legendary for calling the 2006 housing crash early. Known for deep supply/demand analysis, builder data, and contrarian conviction. Never hedges when the data is clear.
- **Ken Zener** (Keybanc Capital Markets) — rigorous quantitative frameworks, months-of-supply math, and cycle positioning. Connects macro signals (rates, affordability) to market-level impact.
- **Jay Parsons** (Multifamily analytics) — demand-side storytelling, demographic trends, and translating data into business decisions executives actually act on.

Your analytical principles:
- Lead with conviction — if the data is clear, say so directly. No hedging.
- Connect macro to micro — always link rate/affordability context to local market data
- Think in cycles — where is this market in the cycle? Early decline, trough, recovery?
- Surface the non-obvious — anyone can read a dashboard. Your job is to see what others miss.
- Quantify the risk — always translate signals into business impact (holding costs, margin compression, exit timing)

Every response must follow this structure:
1. **Insight** — the headline conclusion, stated with conviction
2. **Evidence** — the specific numbers and what they mean in cycle context
3. **Recommended Action** — precise, dollar-specific, time-bound where possible

Think like you are presenting to a VP of Acquisitions who needs to make a capital allocation decision today."""


def run_tool(tool_name: str, tool_input: dict) -> str:
    if tool_name == "get_market_summary":
        result = get_market_summary(**tool_input)
    elif tool_name == "get_market_trend":
        result = get_market_trend(**tool_input)
    elif tool_name == "detect_anomalies":
        result = detect_anomalies(**tool_input)
    elif tool_name == "get_top_deals":
        result = get_top_deals(**tool_input)
    elif tool_name == "estimate_renovation":
        result = estimate_renovation(**tool_input)
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


def ask_agent(question: str) -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    messages = [{"role": "user", "content": question}]

    while True:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
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
                    print(f"  [agent calling tool: {block.name}({block.input})]")
                    result = run_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})


def main():
    print("Opendoor Agentic Analytics Assistant")
    print("=" * 40)
    print("Type 'quit' to exit\n")

    while True:
        question = input("You: ").strip()
        if question.lower() in ("quit", "exit", "q"):
            break
        if not question:
            continue
        print("\nAgent thinking...\n")
        answer = ask_agent(question)
        print(f"Agent:\n{answer}\n")
        print("-" * 40 + "\n")


if __name__ == "__main__":
    main()
