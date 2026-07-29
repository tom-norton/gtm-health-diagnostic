#!/usr/bin/env python3
"""Standalone MCP server exposing the Bowtie diagnostic's three advisor
tools -- get_stage_health, diagnose_conversion_drop, recommend_play -- so
Claude Desktop (or any other MCP client) can query the same dataset the
Streamlit app uses, without going through the app at all.

This is the "author an MCP server" half of the tool-calling story: app.py's
chat advisor CONSUMES these tools over the Anthropic Messages API; this
file exposes the identical handler functions from advisor/tools.py over
MCP, so authoring one didn't mean writing the diagnostic logic twice.

Run directly:
    python mcp_server/server.py

Or point Claude Desktop's config at it -- see the README's MCP setup section
for the exact config block and how to find your Python interpreter path.
"""
import sys
from pathlib import Path

# metrics/, data/, and advisor/ are repo-root siblings of mcp_server/, not
# installed packages -- make sure they're importable regardless of the
# invoking client's working directory (Claude Desktop launches this with
# its own cwd, not necessarily the repo root).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import Literal, Optional

from mcp.server.mcpserver import MCPServer

from advisor.tools import diagnose_conversion_drop as _diagnose_conversion_drop
from advisor.tools import get_stage_health as _get_stage_health
from advisor.tools import recommend_play as _recommend_play
from data.loader import load_data
from metrics import MOTIONS, SEGMENTS, STAGE_ORDER

Stage = Literal[tuple(STAGE_ORDER)]
FromStage = Literal[tuple(STAGE_ORDER[:-1])]
ToStage = Literal[tuple(STAGE_ORDER[1:])]
Segment = Literal[tuple(SEGMENTS)]
Motion = Literal[tuple(MOTIONS)]

# Loaded once at startup against the full, unfiltered dataset -- there is no
# sidebar here to pre-filter it, so every tool call takes its own
# segment/motion/cohort narrowing instead.
_agg_df, _deal_df = load_data()

server = MCPServer(
    name="gtm-bowtie-diagnostic",
    instructions=(
        "Diagnostic tools over a Winning by Design Bowtie funnel dataset "
        "(Awareness through Expansion, EUR ARR, synthetic B2B SaaS data). "
        "Use get_stage_health to check one stage, diagnose_conversion_drop "
        "to investigate one transition's history, and recommend_play for "
        "the canonical intervention once you've located a leak."
    ),
)


@server.tool()
def get_stage_health(
    stage: Stage,
    segment: Optional[Segment] = None,
    motion: Optional[Motion] = None,
    cohort: Optional[str] = None,
) -> dict:
    """Conversion rate in and out of a Bowtie stage, average days spent in
    it, deal volume, churn rate if the stage is postsale, and any anomalies
    (statistically and practically significant conversion drops) touching
    it. Narrow with segment, motion, and/or cohort (e.g. "2025-Q2"); omit
    them for the blended figure across the whole dataset."""
    return _get_stage_health(_deal_df, _agg_df, stage, segment=segment, motion=motion, cohort=cohort)


@server.tool()
def diagnose_conversion_drop(
    from_stage: FromStage,
    to_stage: ToStage,
    segment: Optional[Segment] = None,
    motion: Optional[Motion] = None,
) -> dict:
    """Deep-dive one specific stage-to-stage transition: its current
    conversion rate, the full per-cohort-quarter history, and which
    quarters (if any) are flagged as anomalies by the same two-part test
    (a z-score threshold AND a minimum absolute percentage-point drop) the
    dashboard's Conversion Rates tab uses."""
    return _diagnose_conversion_drop(_deal_df, _agg_df, from_stage, to_stage, segment=segment, motion=motion)


@server.tool()
def recommend_play(leak_stage: Stage) -> dict:
    """Canonical Winning by Design intervention for a leak at the given
    stage, sourced from the same playbook the diagnostic advisor's persona
    uses. Commit has no entry -- it's the pinch point, not a leak stage;
    diagnose Selection->Commit or Commit->Onboarding instead."""
    return _recommend_play(leak_stage)


if __name__ == "__main__":
    server.run()
