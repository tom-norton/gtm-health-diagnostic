#!/usr/bin/env python3
"""Synthetic Bowtie funnel data generator for the GTM Health Diagnostic.

Regenerates bowtie_data.csv from scratch. Deterministic given SEED below --
re-run this script to change the data rather than hand-editing the CSV.

Each (segment, cohort) slice draws from its own RNG stream, seeded off SEED
plus that slice's identity, rather than one shared global stream. That
means tuning one segment's parameters reshuffles only that segment's
numbers -- every other slice stays exactly as it was. With a single shared
stream, changing anything anywhere shifts every draw that follows it,
which makes iterative tuning close to unworkable.

Schema
------
Two record types, distinguished by `record_type`:

  aggregate  Awareness/Education volume, one row per segment per cohort.
             Too large to enumerate per lead, so only entry/exit COUNTS are
             stored. Motion-agnostic: both GTM motions draw from the same
             top-of-funnel pool, and only diverge from Selection onward.

  deal       One row per deal PER STAGE OCCUPIED, from Selection onward.
             A deal that reaches Expansion contributes six rows (Selection,
             Commit, Onboarding, Adoption, Renewal, Expansion), all sharing
             one deal_id. Exactly one of those rows -- wherever the deal's
             journey ends, by reaching Expansion or by churning earlier --
             has an empty stage_exited. app.py's `_deal_snapshot()` filters
             on that to recover one row per deal for ARR/retention math;
             the full multi-row log is used for stage-level conversion and
             velocity math, where one row per deal per stage is exactly
             what's wanted.

Two GTM motions are modelled from Selection onward: Sales-led (MQL/SQL,
multi-threaded, longer cycles, larger deals) and PLG (self-serve entry,
faster cycles, smaller deals, an `activated` flag standing in for whether
the account hit its product activation milestone). Motion mix is
segment-conditional -- SMB skews PLG, Enterprise skews Sales-led -- per the
"sub-$5k deals have to be PLG economically" logic in the advisor's own
persona.

A deliberate, real anomaly is injected: Enterprise Sales-led deals in
2025-Q2 have their Selection->Commit win COUNT forced down to a fraction of
normal (a probability alone doesn't reliably show up at this segment's
per-quarter sample size -- see gen_deals). Every other quarter is left to
plain sampling noise. This gives the z-score anomaly detector on the
Conversion Rates tab something genuine to find, rather than a panel that
always reports a clean bill of health.
"""
import csv
import hashlib
from collections import defaultdict
from datetime import date, timedelta

import numpy as np

SEED = 20260315

STAGE_ORDER = ["Awareness", "Education", "Selection", "Commit",
               "Onboarding", "Adoption", "Renewal", "Expansion"]
SEGMENTS = ["SMB", "Mid-Market", "Enterprise"]
MOTIONS = ["Sales-led", "PLG"]
COHORTS = ["2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4",
           "2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"]
COHORT_START = {
    "2024-Q1": date(2024, 1, 1), "2024-Q2": date(2024, 4, 1),
    "2024-Q3": date(2024, 7, 1), "2024-Q4": date(2024, 10, 1),
    "2025-Q1": date(2025, 1, 1), "2025-Q2": date(2025, 4, 1),
    "2025-Q3": date(2025, 7, 1), "2025-Q4": date(2025, 10, 1),
}

REPS = [
    "Amara Okafor", "Ben Sorensen", "Priya Natarajan", "Liam Fitzgerald",
    "Noor Haddad", "Sofia Marchetti", "Declan Byrne", "Yuki Tanaka",
    "Elena Petrova", "Marcus Webb", "Aisling Kelly", "Rian de Groot",
    "Fatima Zahra", "Callum Reid", "Ingrid Johansson", "Tariq Aziz",
]

COMPANY_ADJ = ["Bright", "Northern", "Blue", "Rapid", "Clear", "Silver",
               "Bold", "Swift", "Prime", "Nova", "Cedar", "Amber", "Vantage",
               "Lucid", "Kestrel", "Harbor", "Solstice", "Meridian"]
COMPANY_NOUN = ["Analytics", "Systems", "Cloud", "Works", "Labs", "Dynamics",
                "Metrics", "Solutions", "Robotics", "Health", "Logistics",
                "Finance", "Commerce", "Data", "Signal", "Studio"]
COMPANY_SUFFIX = ["Inc.", "Ltd.", "GmbH", "B.V.", "Group", "& Co."]

# P(motion == PLG) by segment. SMB skews self-serve; Enterprise skews
# sales-led; sub-segment economics per the advisor's own persona.
MOTION_MIX = {"SMB": 0.65, "Mid-Market": 0.35, "Enterprise": 0.05}

# Lognormal (mean EUR, sigma) by segment + motion. PLG runs below Sales-led
# within the same segment -- lower-touch motion, lower ACV.
ACV_PARAMS = {
    ("SMB", "Sales-led"):        (8_500, 0.35),
    ("SMB", "PLG"):              (4_000, 0.40),
    ("Mid-Market", "Sales-led"): (48_000, 0.35),
    ("Mid-Market", "PLG"):       (26_000, 0.35),
    ("Enterprise", "Sales-led"): (185_000, 0.40),
    ("Enterprise", "PLG"):       (90_000, 0.35),
}

# Selection -> Commit ("win rate") by segment + motion. PLG converts higher
# within a segment -- a stylised nod to PQLs outperforming MQLs.
WIN_RATE = {
    ("SMB", "Sales-led"): 0.32, ("SMB", "PLG"): 0.38,
    ("Mid-Market", "Sales-led"): 0.24, ("Mid-Market", "PLG"): 0.29,
    ("Enterprise", "Sales-led"): 0.20, ("Enterprise", "PLG"): 0.24,
}

# Deliberate injected anomaly -- see module docstring. Forced to a fixed,
# small win COUNT rather than a lower probability or even a lower fraction:
# at this slice's sample size (~40-50 deals/quarter), the natural noise
# floor alone ranges the win rate roughly 8-27% across ordinary quarters
# (~6pp standard error on a ~20% true rate at n~45), so anything short of a
# near-total collapse reads as just another noisy quarter, not an outlier.
ANOMALY_COHORT = "2025-Q2"
ANOMALY_KEY = ("Enterprise", "Sales-led")
ANOMALY_WIN_COUNT = 1

# Post-sale stage-survival rates by segment: (commit->onboard, onboard->adopt,
# adopt->renew, renew->expand). Early gates are shallow and roughly flat
# across segments (a small, real "signed but never onboarded" leak); Renewal
# is where segments diverge and where most churn concentrates, per the
# advisor's own "60-70% of annual churn lands at renewal" benchmark.
SURVIVAL = {
    "SMB":        (0.98, 0.98, 0.97, 0.91),
    "Mid-Market": (0.98, 0.98, 0.97, 0.93),
    "Enterprise": (0.99, 0.99, 0.99, 0.97),
}

# Expansion, once a deal renews: (P(expands), low mult, high mult) applied
# to the deal's own ACV. Calibrated so blended NRR lands ~108-112%, with SMB
# sitting near/under 100% and Enterprise comfortably above -- matching the
# advisor's own NRR-by-segment benchmarks (SMB ~97%, Mid-Market ~108%,
# Enterprise ~118%).
EXPANSION_PARAMS = {
    "SMB": (0.40, 0.10, 0.30),
    "Mid-Market": (0.55, 0.20, 0.45),
    "Enterprise": (0.68, 0.22, 0.50),
}

DAYS_BASE = {
    "Selection":  {"SMB": 10, "Mid-Market": 28, "Enterprise": 55},
    "Commit":     {"SMB": 4,  "Mid-Market": 6,  "Enterprise": 10},
    "Onboarding": {"SMB": 12, "Mid-Market": 20, "Enterprise": 35},
    "Adoption":   {"SMB": 45, "Mid-Market": 60, "Enterprise": 75},
    "Renewal":    {"SMB": 20, "Mid-Market": 25, "Enterprise": 30},
    "Expansion":  {"SMB": 30, "Mid-Market": 40, "Enterprise": 50},
}
AWN_DAYS = {"SMB": 5, "Mid-Market": 7, "Enterprise": 9}
EDU_DAYS = {"SMB": 9, "Mid-Market": 12, "Enterprise": 16}

CSV_COLUMNS = [
    "record_type", "cohort_quarter", "stage_entered", "stage_exited",
    "count_entered", "count_exited", "deal_id", "company_name", "segment",
    "motion", "deal_value", "days_in_stage", "conversion_date", "rep_name",
    "churned", "expansion_revenue", "activated",
]


def slice_rng(*parts):
    """A deterministic, independent RNG stream for one (segment, cohort)
    slice (or any other identity tuple), derived from SEED + parts. Two
    calls with the same parts always return the same stream; two calls
    with different parts never share state, so tuning one slice's
    parameters cannot perturb another's."""
    digest = hashlib.sha256(f"{SEED}|{'|'.join(map(str, parts))}".encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big"))


def lognormal(rng, mean, sigma):
    mu = np.log(mean) - sigma ** 2 / 2
    return float(rng.lognormal(mu, sigma))


def days_for(rng, stage, segment, motion):
    base = DAYS_BASE[stage][segment]
    if motion == "PLG" and stage in ("Selection", "Commit"):
        base *= 0.6
    return round(lognormal(rng, base, 0.4), 1)


def gen_company_name(rng):
    return f"{rng.choice(COMPANY_ADJ)}{rng.choice(COMPANY_NOUN)} {rng.choice(COMPANY_SUFFIX)}"


def gen_aggregate_rows():
    """Awareness/Education volume rows, plus the Selection deal count each
    segment/cohort should produce so the aggregate and deal-level rows tie
    out exactly (Education's count_exited == that Selection deal count)."""
    rows = []
    selection_counts = {}

    base_awareness = {"SMB": 8500, "Mid-Market": 7500, "Enterprise": 4600}
    awn_to_edu = {"SMB": 0.095, "Mid-Market": 0.088, "Enterprise": 0.075}
    edu_to_sel = {"SMB": 0.19, "Mid-Market": 0.16, "Enterprise": 0.115}

    for segment in SEGMENTS:
        for i, cohort in enumerate(COHORTS):
            r = slice_rng("aggregate", segment, cohort)
            growth = 1.0 + 0.025 * i
            awareness = int(base_awareness[segment] * growth * r.uniform(0.90, 1.10))
            education = int(awareness * awn_to_edu[segment] * r.uniform(0.90, 1.10))
            selection_n = max(1, round(education * edu_to_sel[segment] * r.uniform(0.92, 1.08)))
            selection_counts[(segment, cohort)] = selection_n

            rows.append(dict(
                record_type="aggregate", cohort_quarter=cohort,
                stage_entered="Awareness", stage_exited="Education",
                count_entered=awareness, count_exited=education,
                segment=segment, days_in_stage=round(lognormal(r, AWN_DAYS[segment], 0.3), 1),
            ))
            rows.append(dict(
                record_type="aggregate", cohort_quarter=cohort,
                stage_entered="Education", stage_exited="Selection",
                count_entered=education, count_exited=selection_n,
                segment=segment, days_in_stage=round(lognormal(r, EDU_DAYS[segment], 0.3), 1),
            ))
    return rows, selection_counts


def _row(deal_id, cohort, stage_entered, stage_exited, segment, motion,
         deal_value, days_in_stage, conv_date, rep, company, churned,
         expansion_revenue, activated):
    return dict(
        record_type="deal", cohort_quarter=cohort,
        stage_entered=stage_entered, stage_exited=stage_exited,
        deal_id=deal_id, company_name=company, segment=segment, motion=motion,
        deal_value=deal_value, days_in_stage=days_in_stage,
        conversion_date=conv_date.isoformat(), rep_name=rep,
        churned=churned, expansion_revenue=expansion_revenue,
        activated="" if activated is None else activated,
    )


def gen_deals(selection_counts):
    rows = []
    deal_seq = 0

    for segment in SEGMENTS:
        for cohort in COHORTS:
            r = slice_rng("deals", segment, cohort)
            n = selection_counts[(segment, cohort)]
            motions = ["PLG" if r.random() < MOTION_MIX[segment] else "Sales-led"
                       for _ in range(n)]

            # Deliberate, forced anomaly for the flagged slice -- see module
            # docstring for why this overrides the count rather than the
            # per-deal probability.
            forced_wins = None
            if cohort == ANOMALY_COHORT and segment == ANOMALY_KEY[0]:
                flagged_idx = [i for i, m in enumerate(motions) if m == ANOMALY_KEY[1]]
                n_win = min(ANOMALY_WIN_COUNT, len(flagged_idx))
                forced_wins = set(r.choice(flagged_idx, size=n_win, replace=False)) \
                    if flagged_idx else set()

            for i in range(n):
                deal_seq += 1
                deal_id = f"D-{deal_seq:05d}"
                motion = motions[i]
                rep = str(r.choice(REPS))
                company = gen_company_name(r)
                acv_mean, acv_sigma = ACV_PARAMS[(segment, motion)]
                deal_value = round(lognormal(r, acv_mean, acv_sigma), 2)

                if forced_wins is not None and motion == ANOMALY_KEY[1]:
                    won = i in forced_wins
                else:
                    won = r.random() < WIN_RATE[(segment, motion)]

                activated = None
                if motion == "PLG":
                    activated = bool(r.random() < (0.80 if won else 0.40))

                cursor = COHORT_START[cohort]
                sel_days = days_for(r, "Selection", segment, motion)
                rows.append(_row(deal_id, cohort, "Selection", "Commit" if won else "",
                                  segment, motion, deal_value, sel_days, cursor, rep, company,
                                  churned=False, expansion_revenue=0, activated=activated))
                if not won:
                    continue
                cursor += timedelta(days=sel_days)

                c2o, o2a, a2r, r2e = SURVIVAL[segment]

                commit_days = days_for(r, "Commit", segment, motion)
                onboarded = r.random() < c2o
                rows.append(_row(deal_id, cohort, "Commit", "Onboarding" if onboarded else "",
                                  segment, motion, deal_value, commit_days, cursor, rep, company,
                                  churned=(not onboarded), expansion_revenue=0, activated=activated))
                if not onboarded:
                    continue
                cursor += timedelta(days=commit_days)

                onb_days = days_for(r, "Onboarding", segment, motion)
                adopted = r.random() < o2a
                rows.append(_row(deal_id, cohort, "Onboarding", "Adoption" if adopted else "",
                                  segment, motion, deal_value, onb_days, cursor, rep, company,
                                  churned=(not adopted), expansion_revenue=0, activated=activated))
                if not adopted:
                    continue
                cursor += timedelta(days=onb_days)

                adp_days = days_for(r, "Adoption", segment, motion)
                renewed = r.random() < a2r
                rows.append(_row(deal_id, cohort, "Adoption", "Renewal" if renewed else "",
                                  segment, motion, deal_value, adp_days, cursor, rep, company,
                                  churned=(not renewed), expansion_revenue=0, activated=activated))
                if not renewed:
                    continue
                cursor += timedelta(days=adp_days)

                ren_days = days_for(r, "Renewal", segment, motion)
                expanded = r.random() < r2e
                rows.append(_row(deal_id, cohort, "Renewal", "Expansion" if expanded else "",
                                  segment, motion, deal_value, ren_days, cursor, rep, company,
                                  churned=(not expanded), expansion_revenue=0, activated=activated))
                if not expanded:
                    continue
                cursor += timedelta(days=ren_days)

                exp_days = days_for(r, "Expansion", segment, motion)
                exp_prob, exp_low, exp_high = EXPANSION_PARAMS[segment]
                expansion_revenue = 0.0
                if r.random() < exp_prob:
                    expansion_revenue = round(deal_value * r.uniform(exp_low, exp_high), 2)
                rows.append(_row(deal_id, cohort, "Expansion", "",
                                  segment, motion, deal_value, exp_days, cursor, rep, company,
                                  churned=False, expansion_revenue=expansion_revenue,
                                  activated=activated))
    return rows


def validate(agg_rows, deal_rows):
    """Print a summary so a re-run can be sanity-checked without opening the
    CSV."""
    deal_ids = {r["deal_id"] for r in deal_rows}
    print(f"aggregate rows: {len(agg_rows)}   deal rows: {len(deal_rows)}   "
          f"distinct deals: {len(deal_ids)}")

    POSTSALE = {"Onboarding", "Adoption", "Renewal", "Expansion"}
    snapshot = [r for r in deal_rows if r["stage_exited"] == ""]
    assert len(snapshot) == len(deal_ids), "snapshot must have exactly one row per deal"

    post = [r for r in snapshot if r["stage_entered"] in POSTSALE]
    base_arr = sum(r["deal_value"] for r in post)
    churn_arr = sum(r["deal_value"] for r in post if r["churned"])
    exp_rev = sum(r["expansion_revenue"] for r in post)
    grr = (base_arr - churn_arr) / base_arr * 100
    nrr = (base_arr - churn_arr + exp_rev) / base_arr * 100
    print(f"overall: base ARR EUR {base_arr:,.0f}   GRR {grr:.1f}%   NRR {nrr:.1f}%   "
          f"logo churn {sum(1 for r in post if r['churned']) / len(post) * 100:.1f}%")

    for seg in SEGMENTS:
        seg_post = [r for r in post if r["segment"] == seg]
        seg_base = sum(r["deal_value"] for r in seg_post)
        seg_churn = sum(r["deal_value"] for r in seg_post if r["churned"])
        seg_exp = sum(r["expansion_revenue"] for r in seg_post)
        seg_grr = (seg_base - seg_churn) / seg_base * 100 if seg_base else 0
        seg_nrr = (seg_base - seg_churn + seg_exp) / seg_base * 100 if seg_base else 0
        churn_by_stage = {}
        for r in seg_post:
            if r["churned"]:
                churn_by_stage[r["stage_entered"]] = churn_by_stage.get(r["stage_entered"], 0) + 1
        print(f"  {seg:<12} GRR {seg_grr:5.1f}%  NRR {seg_nrr:5.1f}%  "
              f"churn by stage: {churn_by_stage}")

    entered = defaultdict(int)
    exited = defaultdict(int)
    for r in deal_rows:
        entered[r["stage_entered"]] += 1
        if r["stage_exited"]:
            exited[(r["stage_entered"], r["stage_exited"])] += 1
    for a, b in zip(STAGE_ORDER[2:], STAGE_ORDER[3:]):
        e, x = entered.get(a, 0), exited.get((a, b), 0)
        rate = x / e * 100 if e else 0
        flag = "  <-- 100%!" if e and x == e else ("  <-- 0%!" if e and x == 0 else "")
        print(f"  {a:<11} -> {b:<11} {rate:5.1f}%  (n={e}){flag}")


def main():
    agg_rows, selection_counts = gen_aggregate_rows()
    deal_rows = gen_deals(selection_counts)
    validate(agg_rows, deal_rows)

    with open("bowtie_data.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in agg_rows + deal_rows:
            writer.writerow({col: row.get(col, "") for col in CSV_COLUMNS})
    print(f"\nWrote bowtie_data.csv ({len(agg_rows) + len(deal_rows)} rows)")


if __name__ == "__main__":
    main()
