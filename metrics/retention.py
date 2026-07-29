"""GRR/NRR arithmetic, factored out because it was previously duplicated
across three places in app.py (the summary stats, the Tab 1 KPI row, and the
Tab 4 cohort table) with the same dedup requirement each time."""


def compute_nrr_grr(post_snapshot_slice):
    """`post_snapshot_slice` must already be deduped to one row per deal and
    filtered to postsale stages -- see metrics.snapshot.deal_snapshot(). This
    function does not dedupe for you: pass it the raw multi-row transition
    log and every number it returns will be inflated by however many
    postsale stages each deal reached."""
    base_arr = post_snapshot_slice["deal_value"].sum()
    churn_arr = post_snapshot_slice[post_snapshot_slice["churned"]]["deal_value"].sum()
    exp_arr = post_snapshot_slice["expansion_revenue"].sum()
    grr = (base_arr - churn_arr) / base_arr * 100 if base_arr else 0.0
    nrr = (base_arr - churn_arr + exp_arr) / base_arr * 100 if base_arr else 0.0
    churn_rate_pct = round(post_snapshot_slice["churned"].mean() * 100, 1) if len(post_snapshot_slice) else 0.0
    return {
        "base_arr": float(base_arr),
        "churn_arr": float(churn_arr),
        "expansion_arr": float(exp_arr),
        "grr_pct": round(grr, 1),
        "nrr_pct": round(nrr, 1),
        "churn_rate_pct": churn_rate_pct,
    }
