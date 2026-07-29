"""Plotly figure builders. Only the bowtie diagram lives here as its own
module -- it's complex and reused across the cohort-dropdown re-render. The
simpler per-tab charts stay inline in app.py, built directly against the
filtered dataframe for that tab."""
from .bowtie_chart import build_bowtie_fig
from .palette import CHART_BG, CHART_FONT, ENT_COLOR, HAIRLINE, MM_COLOR, PRESALE_COLOR, POSTSALE_COLOR, SEGMENT_COLORS, SMB_COLOR

__all__ = [
    "build_bowtie_fig",
    "CHART_BG",
    "CHART_FONT",
    "ENT_COLOR",
    "HAIRLINE",
    "MM_COLOR",
    "PRESALE_COLOR",
    "POSTSALE_COLOR",
    "SEGMENT_COLORS",
    "SMB_COLOR",
]
