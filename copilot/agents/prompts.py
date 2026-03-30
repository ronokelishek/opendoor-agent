"""
agents/prompts.py
-----------------
Prompt templates for the Opendoor Pricing & Conversion Copilot reasoning agent.

Design principles:
  - SYSTEM_PROMPT establishes the agent's role, constraints, and output contract
  - ISSUE_REASONING_PROMPT structures the per-issue analysis request
  - All prompts are designed to elicit specific, quantified, business-memo output
  - No hallucination: model is explicitly instructed to stay grounded in provided data
"""

# ---------------------------------------------------------------------------
# System prompt — establishes identity and constraints
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a Senior Analytics Advisor embedded in Opendoor's \
Pricing & Operations team.

Your role is to analyze detected business issues and produce structured, \
actionable briefings for Opendoor's weekly business review. Your audience is \
senior leadership — VP of Pricing, VP of Operations, VP of Growth — who need \
concise, evidence-backed analysis they can act on immediately.

Core principles you must follow:
1. GROUNDED IN DATA: Every claim must reference specific metrics from the issue \
packet. Do not speculate beyond what the data supports.
2. BUSINESS-FIRST LANGUAGE: Lead with business impact, not technical observations. \
Say "sellers are rejecting 1 in 5 more offers this week" not "acceptance_rate \
declined by 0.12".
3. QUANTIFY IMPACT: Use the numbers provided. Convert ratios to counts where \
meaningful (e.g., "~15 fewer closes per week at current volume").
4. OPERATIONAL SPECIFICITY: Recommendations must be specific enough to assign \
to a team and execute this week. Avoid vague suggestions like "investigate further."
5. CALIBRATED CONFIDENCE: Explicitly state when the data is sufficient for high \
confidence versus when more investigation is needed.

You operate within Opendoor's business context:
- Opendoor acquires homes directly from sellers, holds them, and resells
- Acquisition margin (typically 3-5%) is thin — a 2pp compression is material
- Funnel: Seller Lead → Offer Generated → Offer Accepted → Close
- Key risk: pricing model misalignment (AVM drift) causes cascading issues
- Markets are segmented by home tier: entry_level, mid_tier, premium

Output format: Respond only with valid JSON matching the schema specified in \
each request. Do not include markdown formatting, preamble, or trailing text."""


# ---------------------------------------------------------------------------
# Per-issue reasoning prompt
# ---------------------------------------------------------------------------

ISSUE_REASONING_PROMPT = """You are analyzing a detected business issue for \
Opendoor's weekly business review.

Issue packet:
{issue_packet}

Produce a structured analysis as a JSON object with exactly these keys:

{{
  "executive_summary": "<2-3 sentences, business-first, quantified where possible>",
  "root_causes": [
    "<Root cause 1 — specific, grounded in evidence>",
    "<Root cause 2 — specific, grounded in evidence>",
    "<Root cause 3 (optional) — include only if data supports a third cause>"
  ],
  "business_impact": "<2-3 sentences quantifying the business impact using metrics from the packet>",
  "recommended_actions": [
    "<Action 1 — specific, assignable, executable this week>",
    "<Action 2 — specific, assignable, executable this week>",
    "<Action 3 — specific, assignable, executable this week>"
  ],
  "confidence": "<High | Medium-High | Medium>",
  "owner": "<pricing | operations | growth | market-ops>"
}}

Rules:
- executive_summary: Start with the business problem, not the symptom. \
Reference the specific market and segment. Include the primary metric deviation.
- root_causes: 2-3 bullets grounded ONLY in the evidence provided. Do not \
speculate about causes not supported by the data.
- business_impact: Quantify using numbers from the metrics_snapshot. \
Convert rates to absolute counts where helpful (e.g., "at {volume} offers/week, \
this translates to ~N fewer acceptances").
- recommended_actions: Exactly 3 actions. Each must name a responsible team, \
specify a concrete deliverable, and include a timeframe (e.g., "by EOD Friday").
- confidence: Use "High" only if multiple independent signals corroborate the issue.
- owner: The single team best positioned to resolve the primary issue.

Respond with valid JSON only. No markdown, no preamble."""


# ---------------------------------------------------------------------------
# Batch summary prompt (for the executive overview section)
# ---------------------------------------------------------------------------

BATCH_SUMMARY_PROMPT = """You are preparing the executive overview for Opendoor's \
weekly business review. You have been given a list of detected issues with their \
individual analyses.

Issue list:
{issues_summary}

Write a 3-5 sentence executive overview that:
1. States the number of issues detected and their severity breakdown
2. Identifies the highest-priority concern and why it matters most
3. Notes which market(s) are healthy and can serve as comparison baselines
4. Closes with a single priority recommendation for leadership

Tone: Direct, data-driven, no hedging. Senior VP audience.

Respond with a single paragraph of plain text (no JSON, no bullets)."""


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def format_issue_packet(issue) -> str:
    """
    Convert an Issue object into a structured text packet for the LLM prompt.
    Formats numbers as percentages and includes business context.
    """
    import json

    def pct(v):
        if v is None:
            return "N/A"
        return f"{v * 100:.2f}%"

    def fmt(v):
        if v is None:
            return "N/A"
        if isinstance(v, float):
            return f"{v:.4f}"
        return str(v)

    snapshot = issue.metrics_snapshot
    deltas = issue.wow_deltas

    # Format snapshot with human-readable labels
    formatted_snapshot = {}
    for k, v in snapshot.items():
        if "rate" in k or "pct" in k or "margin" in k or "efficiency" in k:
            formatted_snapshot[k] = pct(v)
        else:
            formatted_snapshot[k] = fmt(v)

    formatted_deltas = {}
    for k, v in deltas.items():
        if v is not None:
            if "rate" in k or "pct" in k or "margin" in k or "efficiency" in k:
                sign = "+" if v >= 0 else ""
                formatted_deltas[k] = f"{sign}{v * 100:.2f}pp WoW"
            elif "days" in k:
                sign = "+" if v >= 0 else ""
                formatted_deltas[k] = f"{sign}{v:.1f} days WoW"
            else:
                formatted_deltas[k] = fmt(v)

    packet = {
        "issue_type": issue.issue_type,
        "title": issue.title,
        "market": issue.market,
        "segment": issue.segment,
        "severity": issue.severity,
        "week_start": issue.week_start,
        "confidence": issue.confidence,
        "evidence": issue.evidence,
        "metrics_snapshot": formatted_snapshot,
        "wow_deltas": formatted_deltas,
    }

    return json.dumps(packet, indent=2)


def build_issue_reasoning_prompt(issue) -> str:
    """Build the full reasoning prompt for a single issue."""
    issue_packet = format_issue_packet(issue)
    return ISSUE_REASONING_PROMPT.format(issue_packet=issue_packet)


def build_batch_summary_prompt(issues, analyses) -> str:
    """Build the batch summary prompt from a list of issues and their analyses."""
    lines = []
    for issue, analysis in zip(issues, analyses):
        lines.append(
            f"- [{issue.severity.upper()}] {issue.title}: "
            f"{analysis.get('executive_summary', 'No summary available')[:150]}..."
        )
    issues_summary = "\n".join(lines) if lines else "No issues detected."
    return BATCH_SUMMARY_PROMPT.format(issues_summary=issues_summary)
