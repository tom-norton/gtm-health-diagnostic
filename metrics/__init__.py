"""Pure computation over the Bowtie transition log -- no Streamlit import
anywhere in this package. app.py, advisor/tools.py, and mcp_server/server.py
all call the same functions here, so the dashboard, the chat advisor, and
the standalone MCP server can never disagree about a number."""
from .anomalies import compute_conversion_anomalies
from .bowtie import compute_bowtie
from .constants import (
    AGGREGATE_STAGES,
    DEAL_STAGES,
    MIN_ABS_DROP_PP,
    MIN_COHORTS_FOR_ZSCORE,
    MOTIONS,
    PRESALE,
    POSTSALE,
    SEGMENTS,
    STAGE_ORDER,
    ZSCORE_THRESHOLD,
)
from .retention import compute_nrr_grr
from .snapshot import deal_snapshot
from .stages import compute_conversion_rates, compute_stage_volumes
from .summary import compute_headline_snapshot

__all__ = [
    "compute_conversion_anomalies",
    "compute_bowtie",
    "compute_conversion_rates",
    "compute_headline_snapshot",
    "compute_nrr_grr",
    "compute_stage_volumes",
    "deal_snapshot",
    "AGGREGATE_STAGES",
    "DEAL_STAGES",
    "MIN_ABS_DROP_PP",
    "MIN_COHORTS_FOR_ZSCORE",
    "MOTIONS",
    "PRESALE",
    "POSTSALE",
    "SEGMENTS",
    "STAGE_ORDER",
    "ZSCORE_THRESHOLD",
]
