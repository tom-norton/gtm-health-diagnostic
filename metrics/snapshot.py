"""The one function every ARR/retention calculation in this codebase must
go through -- see its docstring for why."""


def deal_snapshot(deal_data):
    """One row per distinct deal_id: its terminal stage, whether that means
    reaching Expansion or churning earlier. Every deal's chain of per-stage
    rows has exactly one row with an empty stage_exited -- the stage where
    its journey ended -- which is what this filters on. Use this, never the
    full per-stage log, for ARR / NRR / GRR / churn-rate math: summing
    deal_value across a deal's multiple stage rows counts its ARR once per
    stage it reached rather than once."""
    return deal_data[deal_data["stage_exited"] == ""]
