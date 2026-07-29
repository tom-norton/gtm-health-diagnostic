# GTM Health Diagnostic

A diagnostic dashboard for B2B SaaS revenue teams, built on the Winning by Design Bowtie framework, with an AI advisor that reads the filtered data and names where the revenue engine is leaking.

**[Live demo](https://gtm-health-diagnostic-eumwua5bjieoxuxtrwyaar.streamlit.app/)** · Built by [Tom Norton](https://www.linkedin.com/in/tom-p-norton/)

![The bowtie funnel across all eight stages](docs/img/bowtie.png)

## Why this exists

Eleven years in B2B SaaS customer success and account management teaches you one thing clearly: most GTM problems that land on the customer side started three stages earlier on the sales side. Win rates are soft because qualifying criteria are fuzzy. Onboarding churns high because Impact was never captured at Commit. Expansion stalls because nobody proved ROI before pitching the upsell.

The data to catch these problems earlier usually exists. It is buried in a CRM or a BI tool that takes a week to query, and by the time someone pulls it the quarter is over. I built this to make that diagnosis fast, and to make it argue from the right benchmarks rather than from whichever number was easiest to reach.

## What it does

Eight stages across the Bowtie — Awareness, Education, Selection, Commit, Onboarding, Adoption, Renewal, Expansion — filtered by segment, GTM motion, rep and cohort quarter. Two motions are modelled separately from Selection onward: PLG (self-serve entry, an `activated` flag standing in for whether the account hit its product activation milestone) and Sales-led (MQL/SQL, multi-threaded, longer cycles). Filtering by motion, or asking the advisor a PLG-specific question, draws on real per-motion win rates and activation data rather than a label the dataset can't back up.

| Tab | What it answers |
|---|---|
| **Bowtie Funnel** | Where does volume collapse, and what is the ARR on each side of the Commit knot? |
| **Conversion Rates** | Which stage-to-stage transition is underperforming, and is any quarter a genuine outlier? |
| **Days in Stage** | Where are deals sitting too long, and is the average hiding a bimodal distribution? |
| **NRR / GRR by Cohort** | Is retention structural or is one quarter dragging the average? |
| **Stage Velocity** | Are cycle times degrading over time, or was one quarter noisy? |

Below the tabs, the **RevOps Diagnostic Advisor** (Claude Sonnet 4.6, adaptive thinking) receives the current filtered snapshot plus your ACV band, segment and GTM motion. It applies Bowtie benchmarks, anchors every number to your context before citing it, distinguishes structural trends from one-quarter blips, and declines to invent benchmarks it does not have sourced.

## Architecture

```mermaid
flowchart LR
    CSV[bowtie_data.csv<br/>synthetic transition log] --> LOAD[load_data<br/>cached]
    LOAD --> FILTER[Sidebar filters<br/>segment / motion / cohort / rep]
    FILTER --> METRICS[Metric layer<br/>stage volumes · conversion<br/>NRR/GRR · z-score anomalies]
    METRICS --> TABS[5 Plotly tabs]
    METRICS --> SNAP[compute_summary_stats<br/>JSON snapshot]
    PROFILE[Company profile<br/>ACV · segment · motion] --> CTX[build_company_context]
    SNAP --> SYS[System prompt]
    CTX --> SYS
    PERSONA[Advisor persona<br/>WbD benchmarks · SPICED<br/>anchoring rules] --> SYS
    SYS --> API[Anthropic Messages API]
    API --> CHAT[Diagnostic chat]
```

The metric layer is the single source of truth: the same functions feed the charts and the model's context, so the advisor cannot cite a number the dashboard does not show.

## Methodology

**Conversion is measured as flow, not headcount.** A snapshot count tells you how many deals are currently sitting in a stage, which inflates later stages and understates attrition. Every rate here is `deals that exited into the next stage ÷ deals that entered this stage`, applied identically in the bowtie diagram, the conversion tab and the advisor's context.

**Anomalies require two tests, not one.** A quarter is flagged only when it is both at least 1.5σ below that transition's own mean *and* at least 3 percentage points below it. The second test is the one that matters. Where a stage is very stable its standard deviation is tiny, so a pure z-score flags a 0.2-point move as a −2σ outlier — statistically true, operationally noise. Scoring is per transition, never pooled, because a 25% Selection→Commit rate and a 94% Commit→Onboarding rate are both healthy and comparing them would flag the wrong stage every time.

![Anomaly detection flagging a real stage-conversion drop](docs/img/anomalies.png)

**Benchmarks are anchored before they are cited.** The same win rate is healthy at one ACV band and alarming at another. The advisor asks for the missing dimension rather than delivering an unanchored comparison.

## Currency

All deal values, ARR and expansion revenue are **EUR**. The Winning by Design Table 6.2 conversion benchmarks are published in **USD**, so the ACV band selector is labelled as the USD benchmark row it selects rather than silently converted. The advisor is told about the mismatch and asked to flag comparisons that sit close to a band boundary. Converting a sourced benchmark to make a chart tidier would have made the citation wrong.

## Data model

`bowtie_data.csv` is generated by `data/generate.py` — a seeded, committed script, not a hand-edited or opaque file. Re-running it reproduces the exact same CSV; changing a parameter and re-running it is how the dataset gets tuned, not by editing rows.

It holds two record types. Awareness and Education are too large to enumerate per lead, so they appear as `aggregate` rows carrying `count_entered` and `count_exited` per segment per cohort, shared across both GTM motions. From Selection onward, `deal` rows are a genuine **transition log**: a deal that reaches Expansion contributes one row for every stage it occupied — Selection, Commit, Onboarding, Adoption, Renewal, Expansion — all sharing one `deal_id`. Exactly one of those rows, wherever the deal's journey ends, has an empty `stage_exited`; the app's `_deal_snapshot()` filters on that to recover one row per deal for ARR and retention math, while the full multi-row log drives stage-level conversion and velocity math, where one row per deal per stage is exactly what's wanted.

This matters concretely: summing `deal_value` across a deal's postsale rows would count its ARR once per stage it reached rather than once. Every NRR/GRR/churn-rate calculation in `app.py` goes through the snapshot for exactly that reason — it's not a stylistic choice, it's what makes the multi-row model safe to aggregate.

The generator also injects one deliberate, real anomaly — an Enterprise/Sales-led win-rate collapse in a specific quarter — so the anomaly detector on the Conversion Rates tab has something genuine to find rather than a permanently clean bill of health. Every other quarter is left to ordinary sampling noise, which produces its own smaller, unplanned anomalies alongside the injected one.

## What I deliberately did not build

Naming what was left out, and why, matters as much as what shipped.

**No automated decisions about individual customers.** The advisor recommends plays for a human to run. It never scores, ranks or flags a named account for action. Under **GDPR Article 22** a person has the right not to be subject to a decision based solely on automated processing where that decision produces legal or similarly significant effects. A model that decides which accounts get renewal attention — and therefore which quietly do not — is close enough to that line that I would want a documented human review step before crossing it. The human-in-the-loop here is not a disclaimer; it is the reason the tool outputs plays instead of account lists.

**No inference on personal data.** `rep_name` is used only to filter aggregates. There is no rep-level performance ranking, no individual productivity scoring, and no profiling of buyers. Rep-level ranking in particular would be an employment-context inference, which carries a materially higher bar than funnel analysis.

**No claim that this is an EU AI Act high-risk system, and no design that would make it one.** Revenue funnel diagnostics is not a listed high-risk use case. It would move toward one if it were extended to score individuals in an employment context, so that specific extension is off the roadmap rather than merely unimplemented. Transparency obligations still apply: the advisor is clearly labelled as AI-generated output and every number it cites is visible in the dashboard above it.

**No data leaves the session.** The demo runs on synthetic data. Nothing is stored, no chat history is persisted server-side, and there is no analytics or tracking layer. When the HubSpot connector lands, credentials will live in local secrets and never in the repository.

**No unbounded API spend.** The public demo caps advisor questions per browser session, because it runs on a personal API key. It is a courtesy limit, not a security control.

## Tech stack

- **Streamlit** — app shell, filters, chat surface
- **Pandas / NumPy** — stage-transition maths, cohort aggregation, z-score anomaly scoring
- **Plotly** — bowtie diagram and all charts
- **Anthropic API** (`claude-sonnet-4-6`, adaptive thinking) — the diagnostic advisor

## Run locally

```bash
pip install -r requirements.txt
```

Add your Anthropic API key to `.streamlit/secrets.toml`:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
```

Or set it as an environment variable. Then:

```bash
streamlit run app.py
```

The dashboard loads fully without a key; only the advisor requires one.

To regenerate the dataset (e.g. after changing a parameter in `data/generate.py`):

```bash
python data/generate.py
```

Run from the repo root — it overwrites `bowtie_data.csv` in place and prints a validation summary (row counts, GRR/NRR by segment, and a check that no stage transition lands at exactly 100% or 0%).

## Roadmap

In the order I intend to build them:

1. **Move the advisor from context-stuffing to tool calling.** Today it receives a pre-computed JSON snapshot. Exposing `get_stage_health`, `diagnose_conversion_drop` and `recommend_play` as tools lets it query the data it actually needs — a workflow becoming an agent.
2. **Publish those same tools over MCP**, so the diagnostic can be used from Claude Desktop as well as from this app.
3. **HubSpot connector.** A Demo/Live toggle pulling deals from a developer sandbox via the Deals API, mapping pipeline stages to bowtie stages through a custom property. The diagnostic logic does not change; it is a data source swap.

**Done:** a seeded, committed data generator (`data/generate.py`) replaced the opaque CSV — entity-stable `deal_id`s tracing a deal across every stage it occupied, churn weighted to Renewal where the advisor's own benchmarks say it belongs, and separate PLG / Sales-led cohorts so the motion filter and the advisor's PLG-specific reasoning both draw on data that actually exists.

---

Built by [Tom Norton](https://www.linkedin.com/in/tom-p-norton/) · Figures in EUR · Dataset synthetic
