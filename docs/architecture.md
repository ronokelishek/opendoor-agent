# Architecture

## System Overview

```
User / Scheduler
      │
      ├─────────────────────────────────┐
      ▼                                 ▼
┌──────────────────────┐   ┌───────────────────────────┐
│   analytics-agent    │   │      monitor-agent         │
│   (on-demand Q&A)    │   │   (proactive / scheduled)  │
│                      │   │                            │
│  Skills available:   │   │  Skills available:         │
│  · risk-analyzer     │   │  · market-briefing         │
│  · deal-scout        │   │  · deal-scout              │
│  · ivy-zelman        │   │  · ivy-zelman              │
│  · ken-zener         │   │  · ken-zener               │
│  · jay-parsons       │   │  · jay-parsons             │
└──────────┬───────────┘   └──────────────┬────────────┘
           │                              │
           └──────────────┬───────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                       Tool Layer                            │
│                                                             │
│  Data Tools (src/tools/data_loader.py)                      │
│    get_market_summary()    get_market_trend()               │
│    detect_anomalies()                                       │
│                                                             │
│  Risk Tools (src/tools/analyzer.py)                         │
│    score_market_risk()     rank_all_markets()               │
│                                                             │
│  Deal Tools (src/tools/deal_scout.py)                       │
│    get_top_deals()         estimate_renovation()            │
│                                                             │
│  Capital-Light Tools (src/tools/capital_light.py)           │
│    detect_inventory_surges()                                │
│    get_contribution_margin_forecast()                       │
│    rank_top_100_deals()  [+ SEMANTIC_FILTERS layer]         │
│                                                             │
│  Pricing & Conversion Tools (src/tools/pricing_engine.py)  │
│    analyze_pricing_accuracy()                               │
│    analyze_funnel_drop()                                    │
│    generate_pricing_actions()   <-- Decision Packet output  │
│    estimate_business_impact()   <-- unit economics ($)      │
│                                                             │
│  Feedback Loop (src/tools/feedback_tracker.py)             │
│    log_recommendation()         <-- logs every Decision Pkt │
│    record_action_taken()        <-- operator confirms       │
│    record_outcome()             <-- measures actual KPI     │
│    recalibrate_confidence()     <-- updates weights         │
│    get_feedback_summary()       <-- weekly learning report  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                       Data Layer                            │
│    src/data/housing_market.csv                              │
│    copilot/output/synthetic_data.csv                        │
│    (→ Snowflake / BigQuery in production)                   │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      Output Layer                           │
│    Terminal Q&A  │  Daily briefing  │  Deal pipeline JSON   │
│    (→ Web UI)    │  (→ Slack/Email) │  (→ acquisition tool) │
└─────────────────────────────────────────────────────────────┘
```

---

## Agents

### analytics-agent (`agents/analytics-agent.yml`)
- **Trigger:** On-demand — `py -m src.agent` or `/analyze`
- **Role:** Answers natural language questions about market performance
- **Output format:** Insight → Evidence → Recommended Action
- **Tools:** `get_market_summary`, `get_market_trend`, `detect_anomalies`, `get_top_deals`, `estimate_renovation`, `score_market_risk`

### monitor-agent (`agents/monitor-agent.yml`)
- **Trigger:** Daily scheduled or on-demand — `py -m src.monitor` or `/briefing`
- **Role:** Proactive scan — surfaces what matters before anyone asks
- **Output format:** Executive Summary → Risk Rankings → Signals → Actions → Watch List
- **Tools:** All tools including Capital-Light suite
- **Saves to:** `briefings/briefing_YYYY-MM-DD.md`
- **Proactive loop:**
  1. `analyze_pricing_accuracy()` → if HIGH/CRITICAL → `analyze_funnel_drop()` → `generate_pricing_actions()` → `estimate_business_impact(pricing_misalignment)`
  2. `detect_inventory_surges()` → if triggered → `estimate_business_impact(inventory_aging)` → `rank_top_100_deals(capital-light)`
  3. `get_contribution_margin_forecast()` + `rank_all_markets()` → portfolio context
  4. Output: **Decision Packets** per issue (what, financial impact, what to do, who owns it)

---

## Skills

Skills define *how* an agent should reason within a domain. Each skill has a framework, signal set, and output style.

### `skills/market-briefing/` — Daily Market Intelligence
- **When:** Morning briefings, before acquisition meetings
- **How:** Calls `rank_all_markets()` → `detect_anomalies()` → `get_market_summary()` → synthesizes into structured briefing
- **Voice:** Combines Zelman conviction + Zener quant rigor + Parsons demand storytelling
- **Output:** Executive Summary · Risk Rankings · Signals · Actions · Leading Indicators

### `skills/risk-analyzer/` — Acquisition Risk Scoring
- **When:** Before approving acquisitions, capital allocation reviews
- **How:** 5-signal weighted score (1–10) per market

| Signal | Max | Trigger |
|---|---|---|
| Days on market rising | 2 | >5 day MoM increase |
| Sales volume declining | 2 | >10% MoM drop |
| List-to-sale ratio soft | 2 | <0.95 |
| Months of supply high | 2 | >4.5 months |
| Price declining | 2 | <-1% MoM |

- **Score:** 7-10 = HIGH (pause) · 4-6 = MEDIUM (caution) · 1-3 = LOW (go)

### `skills/pricing-engine/` — Pricing & Conversion Decision Engine
- **When:** Any pricing or conversion question; auto-triggered by monitor on HIGH severity signal
- **How:** `analyze_pricing_accuracy()` → `analyze_funnel_drop()` → `generate_pricing_actions()` → `estimate_business_impact()`
- **Output: Decision Packet** — not an insight, a packet ready to act on:

```
Issue:            Offer acceptance dropped 11.8% WoW
Severity:         HIGH — act within 24–72 hours
Evidence:         LSR at 0.95, pricing drifting outside observed acceptance behavior, DOM +6 days
Action:           Narrow offer band -2% to -4% in affected ZIPs by Friday
Financial Impact: ~10 homes/month at risk, $192k margin/month
Expected Outcome: +6–9% acceptance rate improvement within 2–3 weeks
Measurement:      Track LSR and accepted_offer_count vs prior 4-week average
Owner:            Pricing Team
Confidence:       High
```

### `skills/deal-scout/` — ROI Deal Ranking
- **When:** Capital deployment decisions, weekly deal pipeline reviews
- **How:** Generates 100 deals ranked by composite score (ROI + velocity bonus)
- **P&L formula:** `Net Profit = ARV − Acquisition − Reno − Holding − Selling`
- **Renovation tiers:**

| Tier | Cost/sqft | ARV Uplift | Best for |
|---|---|---|---|
| cosmetic | $12–22 | +12% | Fast exits |
| moderate | $28–45 | +25% | Core strategy |
| full_gut | $55–90 | +42% | Max upside |

- **Filters:** market, max capital, min ROI, semantic filter (`"capital-light opportunities"`, `"fast turn deals"`, etc.)

### `skills/ivy-zelman/` — For-Sale Housing Framework *(planned)*
- **When:** For-sale acquisition decisions, builder competition risk
- **Signals:** Builder cancellation rate, new construction vs resale mix, mortgage lock-in effect, affordability index
- **Voice:** Conviction-led, early-warning, contrarian when data is clear

### `skills/ken-zener/` — Capital Markets / Rates Framework *(planned)*
- **When:** Rate sensitivity analysis, capital allocation, spread vs carry decisions
- **Signals:** 30yr rate delta, list-to-sale ratio, rate lock-out seller count, credit availability
- **Voice:** Quantitative, cycle-positioning, connects macro to local data

### `skills/jay-parsons/` — Multifamily / Rental Framework *(planned)*
- **When:** Multifamily markets, rent-vs-own demand shifts, new supply pipeline impact
- **Signals:** Net absorption vs supply, effective rent growth, occupancy trend, lease-up velocity
- **Voice:** Demand storytelling, demographic context, executive-ready decisions

---

## Pricing & Conversion Copilot (`copilot/`)

A separate agentic pipeline focused on Opendoor's seller funnel and pricing accuracy.

```
copilot/data/       → 12-week synthetic data (4 markets × 3 segments)
copilot/metrics/    → KPI definitions + WoW calculations
copilot/detection/  → Deterministic issue detection (no LLM)
copilot/agents/     → Claude reasoning layer (mock fallback)
copilot/reports/    → Executive markdown + JSON alerts + Slack summaries
copilot/output/     → weekly_report.md + alerts.json
```

**Detected issues:**

| Market | Issue | Severity |
|---|---|---|
| Phoenix mid_tier | Pricing misalignment — offers 5.8% above market | HIGH |
| Atlanta all segments | Inventory aging — 22% of homes >90 days DOM | HIGH |
| Dallas | Funnel deterioration — lead-to-offer declining 3%/wk | HIGH |
| Miami | Healthy baseline — no critical issues | PASS |

**Run:** `py -m copilot.main --mock` (no API key needed)

---

## Agentic Loop

```
Question / Trigger
      │
      ▼
Claude thinks: "what data do I need?"
      │
      ▼
Claude calls tool autonomously
      │
      ▼
Tool returns structured dict (JSON-serializable)
      │
      ▼
Claude thinks: "do I need more data?"
      │  (loops if needed — multi-turn tool use)
      ▼
Claude synthesizes using active skill framework:
  Insight → Evidence → Recommended Action
```

---

## Severity Framework

| Severity | SLA | Owner Action |
|---|---|---|
| CRITICAL | Immediate — 24 hours | Escalate to VP Acquisitions. Block new offers until resolved. |
| HIGH | 24–72 hours | Owner produces action plan by next business day |
| MEDIUM | Within one week | Flag for weekly review. Adjust if trend continues. |
| LOW | Informational | Log and monitor. Include in next weekly report. |
| HEALTHY | No action | Continue monitoring. Use as comparison baseline. |

---

## Feedback Loop

The system tracks its own predictions and improves over time:

```
Decision Packet generated
        │
        ▼
log_recommendation()  →  stores rec_id + expected outcome
        │
        ▼  (operator acts)
record_action_taken() →  taken / partial / deferred / rejected
        │
        ▼  (next week: measure actual KPI)
record_outcome()      →  observed vs predicted value
        │
        ▼
recalibrate_confidence() → updates CONFIDENCE_WEIGHTS per issue type
        │
        ▼
get_feedback_summary()   → weekly learning report in briefing
```

**Example:** Predicted +29.9% acceptance recovery → observed +24.1% → accuracy 0.806 → `pricing_misalignment` weight adjusted 0.820 → 0.819. System remains calibrated.

---

## Key Design Decisions

| Decision | Reason |
|---|---|
| Tools return structured dicts | Optimized for LLM reasoning, JSON-serializable |
| Deterministic detection, LLM explanation | Code finds the issue; Claude explains and recommends |
| Explicit severity framework (CRITICAL/HIGH/MEDIUM/LOW) | Maps directly to operational urgency and owner action |
| Skills define reasoning framework | Consistent domain expertise across agent runs |
| Monitor runs without input | True proactive intelligence, not reactive |
| Risk score is numeric (1–10) | Enables ranking, thresholds, capital allocation logic |
| CM + velocity composite score | Aligns with Opendoor 2026 Capital-Light strategy |
| Decision Packets include Expected Outcome | Forward-looking, measurable — not just diagnosis |
| Feedback loop recalibrates confidence weights | System improves as more outcomes are recorded |
| `estimate_business_impact()` on every issue | Translates signals into homes/month, margin dollars |
| Semantic filter layer | Translates business intent → structured query filters |
| Briefings saved as markdown | Human-readable + version-controllable + Slack-ready |
| Mock mode in Copilot | Demo runs without API key — interview-safe |

---

## Production Roadmap

| Phase | Change |
|---|---|
| 1 (current) | CSV data, terminal output, mock mode |
| 2 | Snowflake/BigQuery, scheduled cron, real MLS data |
| 3 | Slack/email delivery, web UI, zip-code level signals |
| 4 | Live pricing feed, real-time inventory alerts, analyst skill SKILL.md files complete |
