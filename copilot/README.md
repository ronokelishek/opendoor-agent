# Opendoor Pricing & Conversion Copilot

A proactive agentic analytics system that monitors real estate market data, detects business issues before they become crises, and generates actionable recommendations — demonstrating the analytics-to-action pipeline for a Senior+ Agentic Analytics Engineer role.

---

## The Business Problem: Proactive vs Reactive Analytics

Traditional analytics tooling answers questions *after* someone asks them. By the time a VP notices a conversion rate on a dashboard, the underlying issue has often been compounding for 2-3 weeks.

This copilot inverts that model:

| Reactive Analytics | This Copilot |
|-------------------|--------------|
| Dashboard → Human notices → Asks question → Gets answer | System detects → Reasons → Acts |
| Latency: Days to weeks | Latency: Minutes (weekly batch) |
| Requires analyst to know what to look for | Codifies institutional knowledge in rules |
| Output: Numbers | Output: Narrative + Actions |

At Opendoor specifically, this matters because:
- **Thin margins**: A 2pp acquisition margin compression on $50M of weekly acquisitions is material — and 100% preventable with early detection
- **AVM drift**: Automated valuation models can silently over/undervalue segments; acceptance rate signals this within 1-2 weeks
- **Cascading failures**: Pricing misalignment → acceptance drop → volume shortfall → missed quarterly targets — the causal chain is predictable once you build the sensors

---

## Architecture

```
                    Raw Data (synthetic_data.py)
                           │
                           ▼
                  Metric Computation Layer
                  (calculations.py)
                  ├── compute_weekly_metrics()
                  └── compute_wow_changes()
                           │
                           ▼
              Deterministic Detection Engine
              (rules.py) — NO LLM HERE
              ├── detect_pricing_misalignment()
              ├── detect_inventory_aging()
              ├── detect_funnel_deterioration()
              └── detect_margin_compression()
                           │
                           ▼
                  Issue objects (issue_types.py)
                  (structured, JSON-serializable)
                           │
                           ▼
               LLM Reasoning Layer (reasoning_agent.py)
               claude-opus-4-6 via Anthropic API
               ├── Structured analysis per issue
               ├── Root causes grounded in evidence
               └── Specific, assignable actions
                           │
                           ▼
                    Report Assembly (build_report.py)
                    ├── Executive markdown report
                    ├── JSON alerts (Slack/PagerDuty)
                    └── Action summaries
```

**Key design decision**: Detection is entirely deterministic. The LLM only sees pre-validated issue packets — it explains and recommends, it does not detect. This means:
- Alerts are reproducible and auditable
- False positive rate is controlled by code, not prompt engineering
- LLM failure modes (hallucination, inconsistency) cannot create ghost alerts

---

## How the LLM Is Used Safely

The reasoning pipeline follows a "detect first, explain second" pattern:

1. **Deterministic detection** runs threshold-based rules against computed metrics
2. Only confirmed issues get forwarded to Claude
3. The prompt includes the specific metric values, evidence bullets, and WoW deltas
4. Claude is instructed to stay grounded in the provided data — no speculation
5. Output is structured JSON, parsed and validated before use

This means Claude's role is: *"Given these confirmed facts, explain what's happening and what to do about it"* — not *"look at this data and find problems."*

---

## The 4 Market Stories Injected in the Data

The synthetic dataset deliberately embeds these patterns to make them detectable:

### 1. Phoenix — Pricing Misalignment (mid_tier only)
Starting week 8, Opendoor's offer prices drift to 4-6% *above* market estimated value in the Phoenix mid_tier segment. The result: seller acceptance rates fall ~12 percentage points from the week-8 baseline. Entry_level and premium segments remain unaffected — making this a segment-specific AVM issue, not a market-wide problem.

**What this tests**: The detection rule fires on *both* conditions simultaneously (price deviation + acceptance drop). Miami mid_tier with stable prices does not trigger it.

### 2. Atlanta — Inventory Aging
Starting week 6, average days-on-market increases progressively (~2.5 days/week) across all Atlanta segments. By week 12, the estimated share of inventory exceeding 90 DOM has risen from ~10% to ~22% — driven by the log-normal DOM distribution model shifting right.

**What this tests**: The detector correctly identifies multi-week trending (not a one-week spike) and fires on both the rate threshold and the sustained-increase pattern.

### 3. Dallas — Funnel Deterioration
Starting week 7, lead-to-offer conversion rate falls ~3% per week (leads arrive, fewer become offers). Offer-to-close also softens slightly. By week 12, funnel efficiency has declined materially from the week-6 baseline.

**What this tests**: The detector fires on the lead-to-offer signal independently of pricing metrics, identifying an operational or product friction problem separate from AVM issues.

### 4. Miami — Healthy Baseline (Control Market)
All Miami metrics are stable with realistic variance. Acceptance rates normal, DOM stable, funnel healthy. Used as the "null hypothesis" to verify detection rules don't over-fire.

**What this tests**: Miami should produce zero or minimal detected issues, validating that the thresholds are calibrated to signal real problems rather than noise.

---

## How to Run

### Prerequisites
```bash
pip install pandas anthropic python-dotenv numpy
```

### Without API Key (Mock Mode)
```bash
cd copilot
python main.py
# or explicitly:
python main.py --mock
```

Mock mode uses pre-written, high-quality responses that match the prompt format — specific, quantified, business-memo tone. Suitable for demos and testing.

### With API Key (Live Mode)
```bash
export ANTHROPIC_API_KEY='your-key-here'
python main.py
# or explicitly:
python main.py --live
```

The system auto-detects whether an API key is present. If found, it calls `claude-opus-4-6`. If not, it falls back to mock mode automatically.

### Run Tests
```bash
cd copilot
python -m pytest tests/ -v
# or:
python -m unittest discover tests/
```

### Generate Synthetic Data Standalone
```bash
python data/synthetic_data.py
# writes: output/synthetic_data.csv
```

---

## Sample Output

After running `main.py`, three files are written to `copilot/output/`:

**`weekly_report.md`** — Full executive briefing:
```
# Opendoor Pricing & Conversion Copilot
## Weekly Business Intelligence Report

Generated: 2024-12-16 09:41 UTC
Issues detected: 8 (2 critical, 3 high, 3 medium)

## 1. Executive Overview
This week's scan detected 8 issues requiring attention...

## 2. Priority Issues
### 1. 🔴 CRITICAL — Pricing Misalignment — Phoenix Mid Tier
Opendoor's offer prices in Phoenix mid_tier are running 5.3% above market
estimated values, triggering a seller acceptance rate collapse to 52.1%...

## 4. Recommended Actions Table
| Priority | Issue | Market | Owner | Action | Timeframe |
|----------|-------|--------|-------|--------|-----------|
| 1 | Pricing Misalignment | Phoenix | pricing | Pull all Phoenix mid_tier... | by EOD tomorrow |
```

**`alerts.json`** — Machine-readable alerts for Slack/PagerDuty integration

**`action_summaries.txt`** — Short per-issue summaries for email/Slack notifications

---

## Repository Structure

```
copilot/
├── data/
│   └── synthetic_data.py       # 12-week synthetic market data generator
├── metrics/
│   ├── definitions.py          # Metric definitions + thresholds (single source of truth)
│   └── calculations.py         # Pandas-based metric computation + WoW deltas
├── detection/
│   ├── issue_types.py           # Issue taxonomy + Issue dataclass
│   └── rules.py                 # Deterministic detection logic (no LLM)
├── agents/
│   ├── prompts.py               # System prompt + per-issue reasoning prompt
│   └── reasoning_agent.py       # Claude API integration + mock fallbacks
├── reports/
│   ├── templates.py             # f-string report templates (markdown, JSON, Slack)
│   └── build_report.py          # Report assembly + file I/O
├── output/                      # Generated reports (gitignored contents)
├── tests/
│   ├── test_metrics.py          # Metric calculation tests (8 test cases)
│   └── test_detection.py        # Detection rule tests (15 test cases)
├── main.py                      # Orchestration entry point
└── README.md
```

---

## Interview Talking Points

### "Why build this instead of using a BI tool?"

BI tools answer questions. This system *asks* them on behalf of the business. The difference is that codified business rules (thresholds, detection logic) encode institutional knowledge that would otherwise live only in the heads of senior analysts. When a senior pricing analyst leaves Opendoor, their pattern-recognition capability for AVM drift doesn't leave with them.

### "How did you handle LLM reliability?"

By not using the LLM for detection. The LLM operates downstream of deterministic rules — it only sees confirmed, quantified issues. If Claude returns something nonsensical, the detection result is unchanged; only the explanation is affected. The mock fallback mode means demos and tests never depend on API availability.

### "How would this scale to production?"

- **Data layer**: Replace `synthetic_data.py` with a warehouse connector (BigQuery/Snowflake) — the `compute_weekly_metrics()` function is table-agnostic
- **Scheduling**: Drop `main.py` into Airflow/Prefect as a weekly DAG; briefings write to S3
- **Alerting**: `alerts.json` plugs directly into Slack's block kit API or PagerDuty's events API
- **Feedback loop**: Add a `feedback/` table where analysts mark issues as valid/invalid — use this to tune thresholds over time

### "What would you add next?"

1. **A/B testing for thresholds** — Run detection at multiple sensitivity levels and measure precision/recall against analyst-labeled historical issues
2. **Trend forecasting** — Add simple linear regression on metric trends to estimate "if this continues, we'll breach X in N weeks"
3. **Cross-market correlation** — If Phoenix and Dallas both show funnel deterioration, this points to a product or platform issue rather than market-specific causes
4. **Anomaly detection** — Statistical process control (e.g., CUSUM) to catch subtle trends that threshold rules miss

### "What makes this demo specifically relevant to Opendoor?"

The metrics and issue types are not generic — they're built around Opendoor's specific business model: iBuying with thin margins, AVM-driven pricing, a multi-stage seller funnel, and geographic market exposure. The four injected stories (AVM drift, DOM aging, funnel deterioration, healthy baseline) reflect the actual risk categories that matter for Opendoor's profitability, not a generic SaaS funnel.
