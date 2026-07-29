import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.loader import load_data


@pytest.fixture(scope="session")
def real_data():
    """The actual committed dataset, loaded once per test session. Used for
    invariant checks (no 100%/0% transitions, snapshot uniqueness) that
    should hold no matter what data/generate.py produces."""
    agg, deal = load_data()
    return agg, deal


def make_deal_rows(rows):
    """Build a minimal deal-log dataframe from plain dicts for hand-checked
    unit tests, filling in any column a test doesn't care about with a
    reasonable default so callers only specify what the test is about."""
    defaults = {
        "cohort_quarter": "2025-Q1",
        "segment": "SMB",
        "motion": "Sales-led",
        "rep_name": "Test Rep",
        "company_name": "Test Co",
        "conversion_date": pd.Timestamp("2025-01-01"),
        "days_in_stage": 10.0,
        "churned": False,
        "expansion_revenue": 0.0,
        "activated": None,
    }
    filled = [{**defaults, **r} for r in rows]
    df = pd.DataFrame(filled)
    df["stage_exited"] = df["stage_exited"].fillna("")
    return df


AGG_COLUMNS = ["cohort_quarter", "stage_entered", "stage_exited",
               "count_entered", "count_exited", "segment", "days_in_stage"]


def make_agg_rows(rows):
    """An empty `rows` list still needs the expected columns present -- an
    empty-list DataFrame has none, which breaks any code that indexes a
    column on it (as compute_conversion_anomalies does even when there are
    no aggregate-stage transitions to score)."""
    defaults = {"segment": "SMB", "days_in_stage": 5.0}
    filled = [{**defaults, **r} for r in rows]
    return pd.DataFrame(filled, columns=AGG_COLUMNS)
