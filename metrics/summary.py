"""The advisor's headline snapshot: the small set of numbers seeded into the
system prompt before any tool call. Deliberately compact -- per-cohort NRR/GRR
history, per-stage days-in-stage, and full transition-by-transition detail
used to be dumped here wholesale (the "context-stuffed" version of this
advisor). They are now retrieved on demand via get_stage_health and
diagnose_conversion_drop (see advisor/tools.py) instead of being pushed into
every request whether the question needs them or not."""
from .anomalies import MIN_ABS_DROP_PP, MIN_COHORTS_FOR_ZSCORE, ZSCORE_THRESHOLD, compute_conversion_anomalies
from .constants import MOTIONS, POSTSALE, SEGMENTS, STAGE_ORDER
from .retention import compute_nrr_grr
from .snapshot import deal_snapshot
from .stages import compute_stage_volumes


def compute_headline_snapshot(deal_data, agg_data):
    """Compute the compact set of headline stats for the chat advisor's
    system prompt, based on whatever slice of the data is currently passed
    in (e.g. the filtered dataframe)."""

    vols = compute_stage_volumes(deal_data, agg_data)

    snapshot = deal_snapshot(deal_data)
    post = snapshot[snapshot["stage_entered"].isin(POSTSALE)]
    overall = compute_nrr_grr(post)

    # Segment performance — Selection->Commit conversion and post-sale churn rate.
    # Selection->Commit is a single row per deal already (Selection is one
    # stage), so no dedup is needed there; churn rate needs the snapshot for
    # the same reason as NRR/GRR above.
    segment_performance = []
    for seg in SEGMENTS:
        seg_df = deal_data[deal_data["segment"] == seg]
        sel = (seg_df["stage_entered"] == "Selection").sum()
        com = ((seg_df["stage_entered"] == "Selection") & (seg_df["stage_exited"] == "Commit")).sum()
        rate = round(com / sel * 100, 1) if sel else 0
        seg_post_snap = snapshot[(snapshot["segment"] == seg) & (snapshot["stage_entered"].isin(POSTSALE))]
        churn_rate = round(seg_post_snap["churned"].mean() * 100, 1) if len(seg_post_snap) else 0
        segment_performance.append({
            "segment": seg,
            "selection_to_commit_rate_pct": rate,
            "post_sale_churn_rate_pct": churn_rate,
        })

    worst_conversion_segment = min(segment_performance, key=lambda r: r["selection_to_commit_rate_pct"])["segment"]
    worst_churn_segment = max(segment_performance, key=lambda r: r["post_sale_churn_rate_pct"])["segment"]

    # Motion performance — grounds PLG-specific questions (activation rate,
    # PQL-equivalent win rate) in real fields instead of the advisor having
    # to reason about a motion the data doesn't actually distinguish.
    motion_performance = []
    for mot in MOTIONS:
        mot_df = deal_data[deal_data["motion"] == mot]
        sel = (mot_df["stage_entered"] == "Selection").sum()
        com = ((mot_df["stage_entered"] == "Selection") & (mot_df["stage_exited"] == "Commit")).sum()
        rate = round(com / sel * 100, 1) if sel else 0
        entry = {"motion": mot, "selection_to_commit_rate_pct": rate, "deal_count": int(sel)}
        if mot == "PLG":
            sel_rows = mot_df[mot_df["stage_entered"] == "Selection"]
            activated = sel_rows["activated"].dropna()
            entry["activation_rate_pct"] = (
                round(activated.mean() * 100, 1) if len(activated) else None
            )
        motion_performance.append(entry)

    # Only the flagged quarters go into context — full history is one
    # diagnose_conversion_drop call away.
    anomaly_flags = [
        a for a in compute_conversion_anomalies(deal_data, agg_data) if a["is_anomaly"]
    ]

    return {
        "currency": "EUR",
        "total_distinct_deals": int(deal_data["deal_id"].nunique()),
        "stage_volumes": {stage: int(vols[stage]) for stage in STAGE_ORDER},
        "overall_grr_pct": overall["grr_pct"],
        "overall_nrr_pct": overall["nrr_pct"],
        "segment_performance": segment_performance,
        "worst_conversion_segment": worst_conversion_segment,
        "worst_churn_segment": worst_churn_segment,
        "motion_performance": motion_performance,
        "conversion_anomalies_flagged": anomaly_flags,
        "anomaly_method": (
            f"per-transition z-score across cohort quarters; flagged only when a "
            f"quarter is BOTH <= {ZSCORE_THRESHOLD} sd below that transition's own "
            f"mean AND >= {MIN_ABS_DROP_PP} percentage points below it, so tiny "
            f"moves in very stable stages are not reported as outliers; "
            f"transitions with < {MIN_COHORTS_FOR_ZSCORE} quarters are unscored. "
            f"An empty list means no stage cleared both tests, NOT that the funnel "
            f"is healthy — call diagnose_conversion_drop or read the conversion "
            f"rates for that."
        ),
        "tools_available": (
            "This snapshot is deliberately compact. Call get_stage_health for a "
            "single stage's conversion in/out, days-in-stage and churn rate; "
            "diagnose_conversion_drop for one transition's full per-cohort "
            "history; recommend_play for the canonical Winning by Design "
            "intervention for a leak stage. All three accept optional segment "
            "and motion narrowing (get_stage_health and diagnose_conversion_drop "
            "also accept a cohort filter)."
        ),
    }
