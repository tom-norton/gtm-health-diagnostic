"""Aggregate figures for the bowtie diagram: per-stage deal/ARR counts and
every consecutive transition's conversion rate, in the shape charts/bowtie_chart.py
needs to draw the eight blocks. Kept separate from metrics.stages because
this is chart-data-prep (count-based ARR estimates), not the canonical
conversion-rate or NRR/GRR numbers used elsewhere."""
from .constants import AGGREGATE_STAGES, STAGE_ORDER
from .stages import compute_stage_volumes

BT_LEFT   = ["Awareness", "Education", "Selection"]
BT_CENTER = "Commit"
BT_RIGHT  = ["Onboarding", "Adoption", "Renewal", "Expansion"]
BT_STAGES = BT_LEFT + [BT_CENTER] + BT_RIGHT


def compute_bowtie(deal_data, agg_data):
    """All metrics needed to render the bowtie for the given data slice."""
    vols = compute_stage_volumes(deal_data, agg_data)

    commit_recs = deal_data[deal_data["stage_entered"] == "Commit"]
    avg_val     = commit_recs["deal_value"].mean() if len(commit_recs) else 0.0

    # Each post-sale stage is counted from its own rows, so the bowtie agrees
    # with the Conversion Rates tab.
    def _stage_count(stage):
        return int((deal_data["stage_entered"] == stage).sum())

    onb_count = _stage_count("Onboarding")
    adp_count = _stage_count("Adoption")
    ren_count = _stage_count("Renewal")
    exp_count = _stage_count("Expansion")

    onb_arr = onb_count * avg_val
    adp_arr = adp_count * avg_val
    ren_arr = ren_count * avg_val

    total_exp = float(deal_data["expansion_revenue"].sum())
    exp_arr   = exp_count * avg_val + total_exp
    nrr       = round(exp_arr / onb_arr * 100, 1) if onb_arr else 0.0

    # Every consecutive transition uses the same exits/entries model.
    rates = {}
    for a, b in zip(BT_STAGES, BT_STAGES[1:]):
        if a in AGGREGATE_STAGES:
            sub     = agg_data[agg_data["stage_entered"] == a]
            entered = int(sub["count_entered"].sum())
            exited  = int(sub["count_exited"].sum())
        else:
            entered = int((deal_data["stage_entered"] == a).sum())
            exited  = int(
                ((deal_data["stage_entered"] == a) &
                 (deal_data["stage_exited"]  == b)).sum()
            )
        rates[(a, b)] = round(exited / entered * 100, 1) if entered else 0.0

    return dict(
        vols=vols, avg_val=avg_val,
        commit_arr=vols.get("Commit", 0) * avg_val,
        onb_count=onb_count, onb_arr=onb_arr,
        adp_count=adp_count, adp_arr=adp_arr,
        ren_count=ren_count, ren_arr=ren_arr,
        exp_count=exp_count,
        total_exp=total_exp, exp_arr=exp_arr, nrr=nrr,
        rates=rates,
    )
