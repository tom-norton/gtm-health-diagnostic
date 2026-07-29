"""Tests over the pure metrics/ layer. Two styles, deliberately: invariant
checks against the real committed dataset (things that must hold no matter
what data/generate.py produces), and hand-constructed tiny dataframes for
exact-value checks where the real dataset's numbers would be too noisy to
assert against directly."""
import pandas as pd
import pytest

from metrics import (
    MOTIONS,
    POSTSALE,
    SEGMENTS,
    STAGE_ORDER,
    compute_conversion_anomalies,
    compute_conversion_rates,
    compute_nrr_grr,
    compute_stage_volumes,
    deal_snapshot,
)
from tests.conftest import make_agg_rows, make_deal_rows


# ── invariants against the real dataset ─────────────────────────────────────

def test_deal_snapshot_is_exactly_one_row_per_deal(real_data):
    _, deal = real_data
    snap = deal_snapshot(deal)
    assert snap["deal_id"].is_unique
    assert set(snap["deal_id"]) == set(deal["deal_id"])


def test_no_transition_lands_at_exactly_100_or_0_percent(real_data):
    """Regression guard for the Phase 1 bug: Renewal->Expansion was 100.0%
    in the original committed CSV. No transition should be a clean 100% or
    0% in a dataset meant to look real."""
    agg, deal = real_data
    rates = compute_conversion_rates(deal, agg)
    for r in rates:
        assert 0.0 < r["rate_pct"] < 100.0, f"{r['from']} -> {r['to']} is {r['rate_pct']}%"


def test_stage_volumes_cover_every_stage(real_data):
    agg, deal = real_data
    vols = compute_stage_volumes(deal, agg)
    for stage in STAGE_ORDER:
        assert vols[stage] > 0, f"{stage} has zero volume"


def test_conversion_rate_chain_ties_to_stage_volumes(real_data):
    """Deals exiting stage A into stage B must equal deals entering stage B
    for every deal-level (non-aggregate) transition -- this is the
    "conversion measured as flow" invariant the README describes."""
    agg, deal = real_data
    rates = compute_conversion_rates(deal, agg)
    vols = compute_stage_volumes(deal, agg)
    for r in rates:
        if r["to"] in ("Education", "Selection"):
            continue  # aggregate-stage entry counts come from a different rollup
        assert r["exited"] == vols[r["to"]], (
            f"{r['from']}->{r['to']} exited={r['exited']} but "
            f"{r['to']} volume={vols[r['to']]}"
        )


def test_every_segment_and_motion_present(real_data):
    _, deal = real_data
    assert set(deal["segment"].unique()) == set(SEGMENTS)
    assert set(deal["motion"].unique()) == set(MOTIONS)


# ── hand-constructed unit tests ──────────────────────────────────────────────

def test_compute_nrr_grr_hand_computed():
    # Three postsale deals, already deduped (as compute_nrr_grr requires):
    # two retained (one with expansion), one churned.
    post = make_deal_rows([
        {"deal_id": "D1", "stage_entered": "Expansion", "stage_exited": "",
         "deal_value": 1000, "churned": False, "expansion_revenue": 200},
        {"deal_id": "D2", "stage_entered": "Expansion", "stage_exited": "",
         "deal_value": 1000, "churned": False, "expansion_revenue": 0},
        {"deal_id": "D3", "stage_entered": "Renewal", "stage_exited": "",
         "deal_value": 1000, "churned": True, "expansion_revenue": 0},
    ])
    result = compute_nrr_grr(post)
    assert result["base_arr"] == 3000
    assert result["churn_arr"] == 1000
    assert result["expansion_arr"] == 200
    assert result["grr_pct"] == pytest.approx((3000 - 1000) / 3000 * 100, abs=0.05)
    assert result["nrr_pct"] == pytest.approx((3000 - 1000 + 200) / 3000 * 100, abs=0.05)
    assert result["churn_rate_pct"] == pytest.approx(100 / 3, abs=0.05)


def test_compute_nrr_grr_on_raw_multirow_log_overcounts():
    """Documents why compute_nrr_grr requires a deduped snapshot: passing
    the raw multi-row log for one deal that reached Expansion counts its
    ARR once per postsale stage it occupied, not once."""
    one_deal_multirow = make_deal_rows([
        {"deal_id": "D1", "stage_entered": "Onboarding", "stage_exited": "Adoption",
         "deal_value": 1000, "churned": False},
        {"deal_id": "D1", "stage_entered": "Adoption", "stage_exited": "Renewal",
         "deal_value": 1000, "churned": False},
        {"deal_id": "D1", "stage_entered": "Renewal", "stage_exited": "Expansion",
         "deal_value": 1000, "churned": False},
        {"deal_id": "D1", "stage_entered": "Expansion", "stage_exited": "",
         "deal_value": 1000, "churned": False},
    ])
    inflated = compute_nrr_grr(one_deal_multirow)
    assert inflated["base_arr"] == 4000  # wrong: same deal counted 4 times

    deduped = compute_nrr_grr(deal_snapshot(one_deal_multirow))
    assert deduped["base_arr"] == 1000  # correct: one deal, one ARR figure


def test_anomaly_requires_both_zscore_and_absolute_drop():
    """A transition that is extremely stable (tiny stdev) should NOT be
    flagged for a fractional move, even though the z-score alone would
    clear the threshold -- this is the fix for the bug where a 0.2-point
    move scored past -2 sigma."""
    deal = make_deal_rows([
        # 5 cohorts, Selection->Commit rate essentially flat at 25%, with a
        # single quarter dipping a fraction of a point.
        *[{"deal_id": f"W{i}", "cohort_quarter": f"2024-Q{i+1}", "stage_entered": "Selection",
           "stage_exited": "Commit"} for i in range(25)],
        *[{"deal_id": f"L{i}", "cohort_quarter": f"2024-Q{i+1}", "stage_entered": "Selection",
           "stage_exited": ""} for i in range(75)],
    ])
    agg = make_agg_rows([])
    anomalies = compute_conversion_anomalies(deal, agg, threshold=-1.5, min_abs_drop_pp=3.0)
    sel_to_commit = [a for a in anomalies if a["from"] == "Selection" and a["to"] == "Commit"]
    assert sel_to_commit, "expected the transition to be scored at all"
    assert not any(a["is_anomaly"] for a in sel_to_commit), (
        "a near-flat series should not be flagged just because its stdev is small"
    )


def test_anomaly_flags_a_real_drop():
    rows = []
    cohorts = [f"2024-Q{i+1}" for i in range(4)] + [f"2025-Q{i+1}" for i in range(4)]
    for i, cq in enumerate(cohorts):
        win_rate = 0.05 if cq == "2025-Q2" else 0.30  # one genuine collapse
        n_win = round(40 * win_rate)
        for w in range(n_win):
            rows.append({"deal_id": f"{cq}-W{w}", "cohort_quarter": cq,
                         "stage_entered": "Selection", "stage_exited": "Commit"})
        for l in range(40 - n_win):
            rows.append({"deal_id": f"{cq}-L{l}", "cohort_quarter": cq,
                         "stage_entered": "Selection", "stage_exited": ""})
    deal = make_deal_rows(rows)
    agg = make_agg_rows([])
    anomalies = compute_conversion_anomalies(deal, agg, threshold=-1.5, min_abs_drop_pp=3.0)
    flagged = [a for a in anomalies if a["is_anomaly"]]
    assert any(a["cohort_quarter"] == "2025-Q2" for a in flagged)


def test_anomaly_skips_transitions_with_too_little_history():
    deal = make_deal_rows([
        {"deal_id": "A", "cohort_quarter": "2024-Q1", "stage_entered": "Selection", "stage_exited": "Commit"},
        {"deal_id": "B", "cohort_quarter": "2024-Q2", "stage_entered": "Selection", "stage_exited": ""},
    ])
    agg = make_agg_rows([])
    anomalies = compute_conversion_anomalies(deal, agg)
    assert anomalies == []
