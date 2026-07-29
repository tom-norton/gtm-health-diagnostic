"""Shared vocabulary for the Bowtie data model. Single source of truth for
stage names, segments and motions -- imported by app.py, advisor/, and
mcp_server/ so all three agree on what a "stage" or "segment" is."""

STAGE_ORDER = [
    "Awareness", "Education", "Selection", "Commit",
    "Onboarding", "Adoption", "Renewal", "Expansion",
]
PRESALE  = STAGE_ORDER[:4]
POSTSALE = STAGE_ORDER[4:]

# Awareness and Education are too large to enumerate per lead, so the dataset
# stores them as a single aggregate row per segment per cohort. Selection
# onward, each deal gets one row per stage it occupied -- see
# metrics.snapshot.deal_snapshot for why that matters for ARR math.
AGGREGATE_STAGES = ["Awareness", "Education"]
DEAL_STAGES = [s for s in STAGE_ORDER if s not in AGGREGATE_STAGES]

SEGMENTS = ["SMB", "Mid-Market", "Enterprise"]

# GTM motion is a deal-level dimension from Selection onward; Awareness/
# Education aggregate rows are motion-agnostic (shared top-of-funnel pool).
MOTIONS = ["Sales-led", "PLG"]

# A quarter is flagged only when it clears BOTH tests -- see
# metrics.anomalies.compute_conversion_anomalies for why the second one
# (an absolute drop, not just a z-score) is load-bearing.
ZSCORE_THRESHOLD = -1.5
MIN_COHORTS_FOR_ZSCORE = 4
MIN_ABS_DROP_PP = 3.0
