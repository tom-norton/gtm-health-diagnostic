# GTM Health Diagnostic

Eleven years in B2B SaaS customer success and account management teaches you one thing clearly: most GTM problems that land on the customer side started three stages earlier on the sales side. Win rates are soft because qualifying criteria are fuzzy. Onboarding churns high because Impact was never captured at Commit. Expansion stalls because nobody proved ROI before pitching the upsell. The data to catch these problems earlier usually exists, but it's buried in a CRM or a BI tool that takes a week to query. I built this to make that diagnosis fast and grounded in the right benchmarks.

## What it does

The dashboard covers eight stages across the Winning by Design Bowtie: Awareness, Education, Selection, Commit, Onboarding, Adoption, Renewal, and Expansion. The sidebar filters by segment, rep, and cohort quarter, and everything updates from there.

**Bowtie Funnel** renders the full funnel as a log-scaled diagram, with pre-sale volume on the left narrowing to Commit and post-sale ARR expanding on the right. Four KPIs sit above it: total awareness leads, end-to-end conversion, GRR, and NRR.

**Conversion Rates** shows stage-to-stage transition rates based on how many deals actually exited into the next stage, not a static snapshot count. You can cut the Selection-to-Commit rate by segment.

**Days in Stage** shows average time per stage by segment, with a heatmap and a violin distribution so outliers aren't hidden inside the average.

**NRR / GRR by Cohort** tracks gross and net retention quarter by quarter, with an ARR waterfall showing base, churn, and expansion together.

**Stage Velocity** shows whether cycle times are improving or degrading across cohorts, with a heatmap of avg days per stage per quarter to spot structural slowdowns.

Below the tabs is the RevOps Diagnostic Advisor, powered by the Anthropic API (Claude Sonnet). It has the current filtered data snapshot in context, along with your ACV band, segment, and GTM motion from the sidebar. The advisor applies Winning by Design Bowtie benchmarks and anchors everything to your specific context before citing a number. It tells you where the leak is, what's likely causing it, and what to run first. It distinguishes structural trends from one-quarter blips and won't invent benchmarks it doesn't have sourced.

## Tech stack

- **Streamlit** for the app shell and sidebar controls
- **Pandas / NumPy** for the stage-transition calculations and cohort aggregations
- **Plotly** for the bowtie diagram and all charts
- **Anthropic API (Claude Sonnet)** for the diagnostic chat

## Data model

The CSV uses a stage-transition log with two record types. Awareness and Education volumes are too large to store per deal, so they appear as `aggregate` rows with `count_entered` and `count_exited` per segment per cohort. From Selection onward, each deal gets its own row with `stage_entered`, `stage_exited`, `days_in_stage`, and deal-level fields including ARR, churn flag, and expansion revenue.

This distinction matters for conversion rates. A snapshot count tells you how many deals are currently sitting in a stage, which inflates later stages and understates attrition. The transition log captures what actually moved, so the rate is exits divided by entries, not a headcount ratio.

## Planned

HubSpot integration is next. The plan is to pull live deal data from a HubSpot sandbox via the Deals API, map HubSpot pipeline stages to bowtie stages using a custom property, and feed that into the same dashboard alongside the demo dataset. The diagnostic logic doesn't need to change; it's a data source swap.

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

The dashboard loads fully without the key. The advisor shows a friendly error until it's configured.

## What I'd build next

A custom MCP server exposing the diagnostic logic as callable tools, so the advisor can query the data directly rather than relying on a pre-computed snapshot in its context window. Anomaly detection on stage conversion drops across cohorts, so the dashboard surfaces problems instead of waiting to be asked. And real HubSpot deal data replacing the synthetic set.
