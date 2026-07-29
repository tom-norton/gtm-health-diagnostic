"""Loads bowtie_data.csv into the two dataframes the rest of the codebase
works with. Kept free of any Streamlit import so app.py, the MCP server, and
pytest can all call it directly -- app.py wraps it in @st.cache_data itself
rather than this module depending on Streamlit."""
from pathlib import Path

import pandas as pd

from metrics.constants import STAGE_ORDER

# Resolved relative to this file, not the caller's cwd, so it works the same
# whether invoked as `streamlit run app.py` from the repo root or as
# `python mcp_server/server.py` from anywhere.
DEFAULT_CSV_PATH = Path(__file__).resolve().parent.parent / "bowtie_data.csv"


def load_data(csv_path=DEFAULT_CSV_PATH):
    """Returns (agg_df, deal_df).

    `deal_df` is a true transition log: a deal that reaches Expansion
    contributes one row per stage occupied (Selection, Commit, Onboarding,
    Adoption, Renewal, Expansion), all sharing one deal_id. Counting rows per
    stage is therefore safe everywhere (each deal has exactly one row per
    stage it passed through), but SUMMING deal_value/expansion_revenue across
    multiple postsale rows for the same deal overcounts its ARR once per
    stage it reached. metrics.snapshot.deal_snapshot() recovers one row per
    deal -- its terminal stage, win or churn -- for exactly that kind of
    ARR/retention math. See data/generate.py for how the CSV is produced."""
    raw = pd.read_csv(csv_path)
    raw["cohort_quarter"] = raw["cohort_quarter"].astype(str)

    agg = raw[raw["record_type"] == "aggregate"].copy()
    agg["count_entered"] = agg["count_entered"].astype(int)
    agg["count_exited"]  = agg["count_exited"].astype(int)
    agg["days_in_stage"] = pd.to_numeric(agg["days_in_stage"], errors="coerce")
    agg = agg[["cohort_quarter", "stage_entered", "stage_exited",
               "count_entered", "count_exited", "segment", "days_in_stage"]]

    deal = raw[raw["record_type"] == "deal"].copy()
    deal["conversion_date"] = pd.to_datetime(deal["conversion_date"])
    deal["churned"]         = deal["churned"].astype(str).str.lower() == "true"
    deal["stage_exited"]      = deal["stage_exited"].fillna("")
    deal["expansion_revenue"] = pd.to_numeric(deal["expansion_revenue"], errors="coerce").fillna(0)
    deal["stage_entered"]     = pd.Categorical(deal["stage_entered"], categories=STAGE_ORDER, ordered=True)
    deal["activated"] = deal["activated"].map({"True": True, "False": False, True: True, False: False})
    deal = deal.drop(columns=["record_type", "count_entered", "count_exited"])

    return agg, deal
