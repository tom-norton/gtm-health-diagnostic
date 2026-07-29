"""The advisor's three tools. Each is a thin wrapper over metrics/ — the
tool layer's job is filtering by the caller's segment/motion/cohort and
shaping the result for the model, not computing anything new.

Used two ways: app.py's tool-use loop calls execute_tool() against whatever
data is currently loaded in the Streamlit session (already filtered by the
sidebar); mcp_server/server.py registers get_stage_health,
diagnose_conversion_drop and recommend_play directly as MCP tools against
the full, unfiltered dataset. Both paths go through the same handler
functions below, so the dashboard, the chat advisor, and the standalone MCP
server can never disagree about what a tool call returns."""
from metrics import (
    DEAL_STAGES,
    MOTIONS,
    SEGMENTS,
    STAGE_ORDER,
    compute_conversion_anomalies,
    compute_conversion_rates,
    compute_stage_volumes,
)

# The Winning by Design play for a leak at each stage, drawn verbatim from
# the advisor persona's own PLAYS section — a structured, machine-readable
# form of the same sourced text, so the model gets a consistent
# recommendation rather than reciting from memory each time. Commit has no
# entry: it's the pinch point itself, not a leak stage — a Commit-adjacent
# problem is really a Selection->Commit or Commit->Onboarding leak.
PLAYS = {
    "Awareness": (
        "Tighten ICP and channel mix; reweight lead scoring toward "
        "high-intent signals (pricing/demo pages) over content downloads. "
        "Fewer, better leads usually beats more."
    ),
    "Education": (
        "Speed-to-lead is the highest-leverage lever — contacting within "
        "the hour dramatically raises qualification odds. Align marketing "
        "and sales on the SQL definition before touching volume."
    ),
    "Selection": (
        "Enforce Critical Event discovery (the SPICED 'CE'), a real "
        "qualification gate, and value-based rather than feature-based "
        "demos, with a clear next step every meeting. Multi-thread: 3+ "
        "engaged stakeholders close far higher than single-threaded deals."
    ),
    "Onboarding": (
        "Define ONE validated activation event and shorten time-to-it "
        "relentlessly. Structured onboarding meaningfully lifts first-year "
        "retention."
    ),
    "Adoption": (
        "Weekly health scoring (usage, feature breadth, engagement) with "
        "proactive check-ins at days 7/30/60/90."
    ),
    "Renewal": (
        "Open renewal 90 days out; T-60 value-review quantifying realized "
        "ROI; T-30 bundle renewal with expansion; fix involuntary churn "
        "(dunning, card updates) separately — it is largely preventable."
    ),
    "Expansion": (
        "Run Land → Adopt → Prove → Expand; most teams skip 'Prove' and "
        "pitch too early. Reliable triggers: crossing ~80% of seat/tier "
        "capacity, a new team adopting, a funding round, deep non-core "
        "feature use, or a QBR where ROI is quantified."
    ),
}


def _apply_filters(deal_data, agg_data, segment=None, motion=None, cohort=None):
    """Aggregate rows have no motion column (see metrics.constants) --
    filtering by motion only ever narrows the deal-level data."""
    d, a = deal_data, agg_data
    if segment:
        d = d[d["segment"] == segment]
        a = a[a["segment"] == segment]
    if motion:
        d = d[d["motion"] == motion]
    if cohort:
        d = d[d["cohort_quarter"] == cohort]
        a = a[a["cohort_quarter"] == cohort]
    return d, a


def get_stage_health(deal_data, agg_data, stage, segment=None, motion=None, cohort=None):
    """Conversion in/out, days-in-stage, churn rate (if postsale), and any
    flagged anomalies touching one stage."""
    d, a = _apply_filters(deal_data, agg_data, segment, motion, cohort)

    vols = compute_stage_volumes(d, a)
    rates = compute_conversion_rates(d, a)
    rate_in = next((r for r in rates if r["to"] == stage), None)
    rate_out = next((r for r in rates if r["from"] == stage), None)

    result = {
        "stage": stage,
        "filters": {"segment": segment, "motion": motion, "cohort": cohort},
        "volume_entering": int(vols.get(stage, 0)),
        "conversion_in_pct": rate_in["rate_pct"] if rate_in else None,
        "conversion_out_pct": rate_out["rate_pct"] if rate_out else None,
    }

    if stage in DEAL_STAGES:
        stage_rows = d[d["stage_entered"] == stage]
        result["avg_days_in_stage"] = (
            round(float(stage_rows["days_in_stage"].mean()), 1) if len(stage_rows) else None
        )
        # No separate "churn rate here" field: in this data model every
        # postsale stage (except Expansion, which is terminal) has exactly
        # two outcomes -- progress to the next stage, or churn -- so churn
        # rate is just 100 - conversion_out_pct. A snapshot-based version
        # would be wrong: a deal's snapshot row at a non-Expansion postsale
        # stage is BY DEFINITION its churn point (only churned deals stop
        # there), so filtering the snapshot to one stage always returns
        # 100% churned regardless of the real attrition rate.
    else:
        agg_rows = a[a["stage_entered"] == stage]
        result["avg_days_in_stage"] = (
            round(float(agg_rows["days_in_stage"].mean()), 1) if len(agg_rows) else None
        )

    anomalies = compute_conversion_anomalies(d, a)
    result["anomalies_touching_this_stage"] = [
        x for x in anomalies if x["is_anomaly"] and (x["from"] == stage or x["to"] == stage)
    ]
    return result


def diagnose_conversion_drop(deal_data, agg_data, from_stage, to_stage, segment=None, motion=None):
    """One transition's current rate, full per-cohort history, and which
    quarters (if any) are flagged as anomalies."""
    d, a = _apply_filters(deal_data, agg_data, segment, motion, cohort=None)

    rates = compute_conversion_rates(d, a)
    current = next((r for r in rates if r["from"] == from_stage and r["to"] == to_stage), None)

    anomalies = compute_conversion_anomalies(d, a)
    history = [x for x in anomalies if x["from"] == from_stage and x["to"] == to_stage]

    return {
        "from_stage": from_stage,
        "to_stage": to_stage,
        "filters": {"segment": segment, "motion": motion},
        "current_rate_pct": current["rate_pct"] if current else None,
        "current_entered": current["entered"] if current else None,
        "per_cohort_history": history,
        "flagged_cohorts": [x for x in history if x["is_anomaly"]],
    }


def recommend_play(leak_stage):
    """Canonical Winning by Design intervention for a leak at the given
    stage. A starting point, not a final answer — the caller should adapt
    it to the specific numbers and context before recommending it."""
    play = PLAYS.get(leak_stage)
    if play is None:
        return {
            "leak_stage": leak_stage,
            "play": None,
            "note": (
                f"No canonical play for {leak_stage} — it's the Commit pinch "
                "point, not a leak stage itself. Diagnose Selection->Commit "
                "(win rate) or Commit->Onboarding (handoff) instead."
            ),
        }
    return {
        "leak_stage": leak_stage,
        "play": play,
        "caveat": (
            "Starting-point intervention from the Winning by Design "
            "playbook. Adapt it to the specific numbers, segment and "
            "motion before presenting it as a final recommendation."
        ),
    }


TOOL_SCHEMAS = [
    {
        "name": "get_stage_health",
        "description": (
            "Get conversion rates in and out of a specific Bowtie stage, "
            "average days spent in that stage, deal volume, and any "
            "flagged anomalies touching it. Use this to check a single "
            "stage's health, optionally narrowed to a segment, GTM motion, "
            "or cohort quarter."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "stage": {"type": "string", "enum": STAGE_ORDER, "description": "The Bowtie stage to check."},
                "segment": {"type": "string", "enum": SEGMENTS, "description": "Optional: narrow to one customer segment."},
                "motion": {"type": "string", "enum": MOTIONS, "description": "Optional: narrow to one GTM motion. Has no effect on Awareness/Education, which have no motion split."},
                "cohort": {"type": "string", "description": "Optional: narrow to one cohort quarter, e.g. '2025-Q2'."},
            },
            "required": ["stage"],
            "additionalProperties": False,
        },
    },
    {
        "name": "diagnose_conversion_drop",
        "description": (
            "Deep-dive one specific stage-to-stage transition: its current "
            "conversion rate, the full per-cohort history, and whether any "
            "cohort is a statistically and practically significant outlier "
            "(the same two-part test used by the Conversion Rates tab's "
            "anomaly panel). Use this when a user asks about a specific "
            "transition, asks 'since when' or 'is this new', or when "
            "get_stage_health flags a stage as anomalous and you need the "
            "history behind it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "from_stage": {"type": "string", "enum": STAGE_ORDER[:-1]},
                "to_stage": {"type": "string", "enum": STAGE_ORDER[1:]},
                "segment": {"type": "string", "enum": SEGMENTS, "description": "Optional: narrow to one customer segment."},
                "motion": {"type": "string", "enum": MOTIONS, "description": "Optional: narrow to one GTM motion."},
            },
            "required": ["from_stage", "to_stage"],
            "additionalProperties": False,
        },
    },
    {
        "name": "recommend_play",
        "description": (
            "Look up the canonical Winning by Design play for a leak at a "
            "given stage. Returns a sourced starting-point intervention, "
            "not a final answer — adapt it to the specific numbers and "
            "context rather than quoting it verbatim. Call this once "
            "you've located the leak stage, instead of reciting a play "
            "from memory."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "leak_stage": {"type": "string", "enum": STAGE_ORDER},
            },
            "required": ["leak_stage"],
            "additionalProperties": False,
        },
    },
]


def execute_tool(name, tool_input, deal_data, agg_data):
    """Dispatch one Anthropic tool_use call to its handler. Returns a plain
    dict -- the caller (app.py's advisor loop, or the Streamlit chat
    handler) is responsible for JSON-encoding it into a tool_result block."""
    if name == "get_stage_health":
        return get_stage_health(deal_data, agg_data, **tool_input)
    if name == "diagnose_conversion_drop":
        return diagnose_conversion_drop(deal_data, agg_data, **tool_input)
    if name == "recommend_play":
        return recommend_play(**tool_input)
    return {"error": f"unknown tool: {name}"}
