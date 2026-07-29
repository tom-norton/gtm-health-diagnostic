"""The diagnostic advisor: persona, tool definitions, and the tool-use loop
that replaced the earlier context-stuffed single-shot prompt."""
from .context import build_company_context, build_system_prompt
from .loop import run_advisor_turn
from .persona import ADVISOR_PERSONA
from .tools import PLAYS, TOOL_SCHEMAS, diagnose_conversion_drop, execute_tool, get_stage_health, recommend_play

__all__ = [
    "ADVISOR_PERSONA",
    "PLAYS",
    "TOOL_SCHEMAS",
    "build_company_context",
    "build_system_prompt",
    "diagnose_conversion_drop",
    "execute_tool",
    "get_stage_health",
    "recommend_play",
    "run_advisor_turn",
]
