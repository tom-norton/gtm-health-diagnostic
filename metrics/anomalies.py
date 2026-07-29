"""Z-score anomaly detection on stage-to-stage conversion, scored per
transition per cohort quarter."""
from .constants import MIN_ABS_DROP_PP, MIN_COHORTS_FOR_ZSCORE, ZSCORE_THRESHOLD
from .stages import compute_conversion_rates

import numpy as np


def compute_conversion_anomalies(deal_data, agg_data, threshold=ZSCORE_THRESHOLD,
                                 min_abs_drop_pp=MIN_ABS_DROP_PP):
    """Flag cohort quarters where a stage's conversion rate is both a
    statistical outlier and a materially large drop.

    A quarter is flagged only when BOTH hold:
      * its z-score is at or below `threshold`, computed against that
        transition's own mean across cohorts, and
      * it sits at least `min_abs_drop_pp` percentage points below that mean.

    The second test is load-bearing, not decorative: where a transition is
    very stable across cohorts its standard deviation is tiny, so a pure
    z-score flags a 0.2-point move as a -2 sigma outlier -- statistically
    true, operationally noise.

    The z-score is computed per transition, never across transitions: a 25%
    Selection->Commit rate and a 94% Commit->Onboarding rate are both healthy
    in context, so pooling them would flag the wrong stage every time. A
    transition is only scored when it has at least MIN_COHORTS_FOR_ZSCORE
    quarters of history and a non-zero standard deviation."""

    cohorts = sorted(set(deal_data["cohort_quarter"]) | set(agg_data["cohort_quarter"]))

    per_cohort = {}
    for cq in cohorts:
        d = deal_data[deal_data["cohort_quarter"] == cq]
        a = agg_data[agg_data["cohort_quarter"] == cq]
        for r in compute_conversion_rates(d, a):
            if r["entered"] == 0:
                continue
            per_cohort.setdefault((r["from"], r["to"]), []).append(
                {"cohort_quarter": cq, "rate_pct": r["rate_pct"], "entered": r["entered"]}
            )

    rows = []
    for (a, b), obs in per_cohort.items():
        if len(obs) < MIN_COHORTS_FOR_ZSCORE:
            continue
        series = np.array([o["rate_pct"] for o in obs], dtype=float)
        mean, std = series.mean(), series.std(ddof=0)
        if std == 0:
            continue
        for o in obs:
            z = (o["rate_pct"] - mean) / std
            drop_pp = float(mean) - o["rate_pct"]
            rows.append({
                "from": a,
                "to": b,
                "transition": f"{a} → {b}",
                "cohort_quarter": o["cohort_quarter"],
                "rate_pct": o["rate_pct"],
                "mean_pct": round(float(mean), 1),
                "drop_pp": round(drop_pp, 1),
                "z_score": round(float(z), 2),
                "entered": o["entered"],
                "is_anomaly": bool(z <= threshold and drop_pp >= min_abs_drop_pp),
            })

    rows.sort(key=lambda r: r["z_score"])
    return rows
