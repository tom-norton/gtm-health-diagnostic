"""Composes the system prompt from the persona, the operator's declared
company context, and the compact headline snapshot (see
metrics.summary.compute_headline_snapshot). No Streamlit import -- the
caller passes plain values read from whatever UI it has."""
import json

from .persona import ADVISOR_PERSONA


def build_company_context(acv_band, segment, motion):
    def val(x):
        return x if x != "Select..." else "not provided"

    return (
        "COMPANY CONTEXT:\n"
        f"- ACV band: {val(acv_band)}\n"
        f"- Segment: {val(segment)}\n"
        f"- GTM motion: {val(motion)}\n"
        "- Currency: all deal values, ARR and expansion revenue in the data "
        "snapshot are EUR. The WbD Table 6.2 ACV bands you benchmark against "
        "are published in USD. Treat the band as the right benchmark row to "
        "use, not as an exact currency match, and say so if a comparison sits "
        "close to a band boundary."
    )


def build_system_prompt(headline_snapshot, company_context):
    return (
        ADVISOR_PERSONA
        + "\n\n"
        + company_context
        + "\n\n"
        + "HEADLINE DATA SNAPSHOT (JSON):\n"
        + json.dumps(headline_snapshot, indent=2, default=str)
    )
