"""Stage-level volume and conversion math. Pure pandas -- no Streamlit
import here, so these are safe to call from the Streamlit app, the advisor's
tools, the MCP server, and pytest, all against the same numbers."""
from .constants import AGGREGATE_STAGES, DEAL_STAGES, STAGE_ORDER

import pandas as pd


def compute_stage_volumes(deal_data, agg_data):
    """Count of deals/leads ENTERING each stage. Awareness/Education come
    from the aggregate rows; Selection onward are counted from deal rows."""
    vols = {}
    for stage in AGGREGATE_STAGES:
        vols[stage] = int(agg_data.loc[agg_data["stage_entered"] == stage, "count_entered"].sum())
    deal_counts = deal_data.groupby("stage_entered", observed=True)["deal_id"].count()
    for stage in DEAL_STAGES:
        vols[stage] = int(deal_counts.get(stage, 0))
    return pd.Series(vols).reindex(STAGE_ORDER)


def compute_conversion_rates(deal_data, agg_data):
    """Per the cohort-flow model: rate = (count that EXITED into the next
    stage) / (count that ENTERED this stage)."""
    rates = []
    for i in range(len(STAGE_ORDER) - 1):
        a, b = STAGE_ORDER[i], STAGE_ORDER[i + 1]
        if a in AGGREGATE_STAGES:
            sub = agg_data[agg_data["stage_entered"] == a]
            entered = int(sub["count_entered"].sum())
            exited  = int(sub["count_exited"].sum())
        else:
            entered = int((deal_data["stage_entered"] == a).sum())
            exited  = int(((deal_data["stage_entered"] == a) & (deal_data["stage_exited"] == b)).sum())
        rate = round(exited / entered * 100, 1) if entered else 0.0
        rates.append({"from": a, "to": b, "entered": entered, "exited": exited, "rate_pct": rate})
    return rates
