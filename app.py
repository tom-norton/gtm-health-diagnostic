import json
import os

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import anthropic

st.set_page_config(
    page_title="GTM Health Diagnostic",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Clay global CSS ───────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');

  html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
  }

  .stApp { background-color: #fffaf0; }

  [data-testid="stSidebar"] {
    background-color: #faf5e8 !important;
    border-right: 1px solid #e5e5e5;
  }
  [data-testid="stSidebar"] h1,
  [data-testid="stSidebar"] h2,
  [data-testid="stSidebar"] h3 {
    font-size: 16px !important;
    font-weight: 600 !important;
    letter-spacing: 0 !important;
    color: #0a0a0a !important;
  }

  h1 {
    font-family: 'Inter', sans-serif !important;
    font-size: 40px !important;
    font-weight: 500 !important;
    line-height: 1.1 !important;
    letter-spacing: -1px !important;
    color: #0a0a0a !important;
  }
  h2 {
    font-size: 32px !important;
    font-weight: 500 !important;
    letter-spacing: -0.5px !important;
    color: #0a0a0a !important;
  }
  h3 {
    font-size: 24px !important;
    font-weight: 600 !important;
    letter-spacing: -0.3px !important;
    color: #0a0a0a !important;
  }

  /* Metric cards */
  [data-testid="stMetric"] {
    background-color: #f5f0e0 !important;
    border-radius: 24px !important;
    padding: 24px 28px !important;
    border: none !important;
  }
  [data-testid="stMetricLabel"] {
    font-size: 12px !important;
    font-weight: 600 !important;
    letter-spacing: 1.5px !important;
    text-transform: uppercase !important;
    color: #6a6a6a !important;
  }
  [data-testid="stMetricValue"] {
    font-size: 32px !important;
    font-weight: 500 !important;
    letter-spacing: -0.5px !important;
    color: #0a0a0a !important;
  }

  /* Tabs */
  .stTabs [data-baseweb="tab-list"] {
    background-color: transparent !important;
    gap: 4px;
  }
  .stTabs [data-baseweb="tab"] {
    background-color: transparent !important;
    border-radius: 9999px !important;
    padding: 8px 16px !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    color: #6a6a6a !important;
    border: none !important;
  }
  .stTabs [aria-selected="true"] {
    background-color: #f5f0e0 !important;
    color: #0a0a0a !important;
  }

  /* Buttons */
  .stButton > button {
    background-color: #0a0a0a !important;
    color: #ffffff !important;
    font-size: 14px !important;
    font-weight: 600 !important;
    border-radius: 12px !important;
    padding: 12px 20px !important;
    height: 44px !important;
    border: none !important;
  }
  .stButton > button:hover { background-color: #1f1f1f !important; }

  /* Inputs */
  .stTextInput > div > div > input,
  .stSelectbox > div > div,
  .stMultiSelect > div > div {
    background-color: #fffaf0 !important;
    border-radius: 12px !important;
    border: 1px solid #e5e5e5 !important;
    color: #0a0a0a !important;
  }

  /* Chat */
  .stChatInput > div {
    background-color: #fffaf0 !important;
    border: 1px solid #e5e5e5 !important;
    border-radius: 12px !important;
  }
  [data-testid="stChatMessage"] {
    background-color: #f5f0e0 !important;
    border-radius: 16px !important;
    padding: 16px !important;
    border: none !important;
  }

  /* Dataframes */
  .stDataFrame {
    border-radius: 16px !important;
    overflow: hidden;
    border: 1px solid #e5e5e5 !important;
  }

  hr { border-color: #e5e5e5 !important; }
  .stCaption { color: #6a6a6a !important; font-size: 13px !important; }

  [data-testid="stSidebar"] [data-testid="stMetric"] {
    background-color: #ebe6d6 !important;
    border-radius: 12px !important;
    padding: 12px 16px !important;
  }
</style>
""", unsafe_allow_html=True)

# ── palette (Clay design system) ─────────────────────────────────────────────
PRESALE_COLOR  = "#ff4d8b"   # brand-pink
POSTSALE_COLOR = "#1a3a3a"   # brand-teal
SMB_COLOR      = "#ffb084"   # brand-peach
MM_COLOR       = "#b8a4ed"   # brand-lavender
ENT_COLOR      = "#e8b94a"   # brand-ochre

CHART_BG   = "#faf5e8"
CHART_FONT = "#0a0a0a"
HAIRLINE   = "#e5e5e5"

STAGE_ORDER = [
    "Awareness", "Education", "Selection", "Commit",
    "Onboarding", "Adoption", "Renewal", "Expansion",
]
PRESALE  = STAGE_ORDER[:4]
POSTSALE = STAGE_ORDER[4:]

# Awareness and Education are too large to enumerate per-deal, so the dataset
# stores them as a single aggregate row per cohort (count_entered/count_exited).
# Selection onward have one row per deal per stage occupied.
AGGREGATE_STAGES = ["Awareness", "Education"]
DEAL_STAGES = [s for s in STAGE_ORDER if s not in AGGREGATE_STAGES]

SEGMENTS = ["SMB", "Mid-Market", "Enterprise"]
SEGMENT_COLORS = {"SMB": SMB_COLOR, "Mid-Market": MM_COLOR, "Enterprise": ENT_COLOR}

# ── bowtie chart constants ────────────────────────────────────────────────────
_BT_LEFT   = ["Awareness", "Education", "Selection"]
_BT_CENTER = "Commit"
_BT_RIGHT  = ["Onboarding", "Adoption", "Expansion"]
_BT_STAGES = _BT_LEFT + [_BT_CENTER] + _BT_RIGHT

_BT_COLORS = {
    "Awareness":  "#ff4d8b",   # brand-pink
    "Education":  "#e8457e",
    "Selection":  "#cc3b70",
    "Commit":     "#1a3a3a",   # brand-teal
    "Onboarding": "#1a4a4a",
    "Adoption":   "#1a5f5f",
    "Expansion":  "#1a7070",
}
_BT_BLK_W = 1.5
_BT_GAP   = 0.40
_BT_MAX_H = 1.0
_BT_MUTED = "#9a9a9a"   # muted-soft

# ── data ─────────────────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    raw = pd.read_csv("bowtie_data.csv")
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
    deal = deal.drop(columns=["record_type", "count_entered", "count_exited"])

    return agg, deal

agg_df, df = load_data()


# ── shared stage-volume / conversion-rate helpers ───────────────────────────
def compute_stage_volumes(deal_data, agg_data):
    """Count of deals/leads ENTERING each stage. Awareness/Education come
    from the aggregate rows; Selection onward are counted from deal rows."""
    vols = {}
    for stage in AGGREGATE_STAGES:
        vols[stage] = int(agg_data.loc[agg_data["stage_entered"] == stage, "count_entered"].sum())
    deal_counts = deal_data.groupby("stage_entered", observed=True)["deal_id"].count()
    for stage in DEAL_STAGES:
        vols[stage] = int(deal_counts.get(stage, 0))
    return pd.Series(vols).reindex(STAGE_ORDER)


def compute_conversion_rates(deal_data, agg_data):
    """Per the cohort-flow model: rate = (count that EXITED into the next
    stage) / (count that ENTERED this stage)."""
    rates = []
    for i in range(len(STAGE_ORDER) - 1):
        a, b = STAGE_ORDER[i], STAGE_ORDER[i + 1]
        if a in AGGREGATE_STAGES:
            sub = agg_data[agg_data["stage_entered"] == a]
            entered = int(sub["count_entered"].sum())
            exited  = int(sub["count_exited"].sum())
        else:
            entered = int((deal_data["stage_entered"] == a).sum())
            exited  = int(((deal_data["stage_entered"] == a) & (deal_data["stage_exited"] == b)).sum())
        rate = round(exited / entered * 100, 1) if entered else 0.0
        rates.append({"from": a, "to": b, "entered": entered, "exited": exited, "rate_pct": rate})
    return rates


# ── bowtie helpers ────────────────────────────────────────────────────────────
def _compute_bowtie(deal_data, agg_data):
    """All metrics needed to render the bowtie for the given data slice."""
    vols = compute_stage_volumes(deal_data, agg_data)

    commit_recs = deal_data[deal_data["stage_entered"] == "Commit"]
    avg_val     = commit_recs["deal_value"].mean() if len(commit_recs) else 0.0

    onb_recs  = deal_data[deal_data["stage_entered"] == "Onboarding"]
    onb_count = len(onb_recs)
    onb_arr   = onb_count * avg_val

    adp_count = int((onb_recs["churned"] == False).sum())
    adp_arr   = adp_count * avg_val

    total_exp = float(deal_data["expansion_revenue"].sum())
    exp_arr   = adp_arr + total_exp
    nrr       = round(exp_arr / onb_arr * 100, 1) if onb_arr else 0.0

    PAIRS = [
        ("Awareness", "Education"), ("Education", "Selection"),
        ("Selection", "Commit"),    ("Commit",    "Onboarding"),
    ]
    rates = {}
    for a, b in PAIRS:
        if a in AGGREGATE_STAGES:
            sub     = agg_data[agg_data["stage_entered"] == a]
            entered = int(sub["count_entered"].sum())
            exited  = int(sub["count_exited"].sum())
        else:
            entered = int((deal_data["stage_entered"] == a).sum())
            exited  = int(
                ((deal_data["stage_entered"] == a) &
                 (deal_data["stage_exited"]  == b)).sum()
            )
        rates[(a, b)] = round(exited / entered * 100, 1) if entered else 0.0

    rates[("Onboarding", "Adoption")] = (
        round(adp_count / onb_count * 100, 1) if onb_count else 0.0
    )
    rates[("Adoption", "Expansion")]  = nrr

    return dict(
        vols=vols, avg_val=avg_val,
        commit_arr=vols.get("Commit", 0) * avg_val,
        onb_count=onb_count, onb_arr=onb_arr,
        adp_count=adp_count, adp_arr=adp_arr,
        total_exp=total_exp, exp_arr=exp_arr, nrr=nrr,
        rates=rates,
    )


def _log_h(vol, ref, max_h=_BT_MAX_H):
    """Log-normalised half-height so all stages remain visible."""
    if ref <= 0 or vol <= 0:
        return max_h * 0.04
    return np.log1p(vol) / np.log1p(ref) * max_h


def _build_bowtie_fig(m, subtitle="All Cohorts"):
    ref = m["vols"].get("Awareness", 1)
    avg = m["avg_val"]

    eff = {
        "Awareness":  m["vols"].get("Awareness", 0),
        "Education":  m["vols"].get("Education", 0),
        "Selection":  m["vols"].get("Selection", 0),
        "Commit":     m["vols"].get("Commit", 0),
        "Onboarding": m["onb_count"],
        "Adoption":   m["adp_count"],
        "Expansion":  int(m["exp_arr"] / avg) if avg else 0,
    }
    H = {s: _log_h(eff.get(s, 0), ref) for s in _BT_STAGES}

    X = {}; x = 0.0
    for s in _BT_STAGES:
        X[s] = x; x += _BT_BLK_W + _BT_GAP

    RATE_PAIRS = [
        ("Awareness", "Education"), ("Education", "Selection"),
        ("Selection", "Commit"),    ("Commit",    "Onboarding"),
        ("Onboarding", "Adoption"), ("Adoption",  "Expansion"),
    ]

    fig = go.Figure()

    for i, s in enumerate(_BT_STAGES[:-1]):
        nxt = _BT_STAGES[i + 1]
        x0, x1 = X[s] + _BT_BLK_W, X[nxt]
        h0, h1 = H[s], H[nxt]
        fig.add_trace(go.Scatter(
            x=[x0, x1, x1, x0, x0], y=[h0, h1, -h1, -h0, h0],
            fill="toself", fillcolor=_BT_COLORS[s], opacity=0.28,
            line=dict(width=0), mode="lines",
            showlegend=False, hoverinfo="skip",
        ))

    for s in _BT_STAGES:
        x0, x1 = X[s], X[s] + _BT_BLK_W
        h   = H[s]
        idx = _BT_STAGES.index(s)
        v   = m["vols"].get(s, 0)

        if s in _BT_LEFT:
            htxt = f"<b>{s}</b><br>Deals: {v:,}"
        elif s == _BT_CENTER:
            htxt = f"<b>Commit</b><br>Deals: {v:,}<br>ARR: ${m['commit_arr']:,.0f}"
        elif s == "Onboarding":
            htxt = f"<b>Onboarding</b><br>Deals: {m['onb_count']:,}<br>ARR: ${m['onb_arr']:,.0f}"
        elif s == "Adoption":
            htxt = (f"<b>Adoption (GRR)</b><br>Retained: {m['adp_count']:,}"
                    f"<br>ARR: ${m['adp_arr']:,.0f}")
        else:
            htxt = (f"<b>Expansion (NRR)</b><br>ARR: ${m['exp_arr']:,.0f}"
                    f"<br>NRR: {m['nrr']:.1f}%<br>Expansion rev: ${m['total_exp']:,.0f}")

        if idx > 0:
            r_in = m["rates"].get((_BT_STAGES[idx - 1], s))
            if r_in is not None:
                sfx = "% NRR" if s == "Expansion" else "%"
                htxt += f"<br>Conv in: {r_in:.1f}{sfx}"
        if idx < len(_BT_STAGES) - 1:
            r_out = m["rates"].get((s, _BT_STAGES[idx + 1]))
            if r_out is not None:
                sfx = "% NRR" if _BT_STAGES[idx + 1] == "Expansion" else "%"
                htxt += f"<br>Conv out: {r_out:.1f}{sfx}"

        fig.add_trace(go.Scatter(
            x=[x0, x1, x1, x0, x0], y=[h, h, -h, -h, h],
            fill="toself", fillcolor=_BT_COLORS[s],
            line=dict(color="white", width=0.7), mode="lines",
            showlegend=False,
            hovertemplate=htxt + "<extra></extra>",
            name=s,
        ))

        if s in _BT_LEFT:
            lbl = f"<b>{s}</b><br>{v:,} deals"
        elif s == _BT_CENTER:
            lbl = f"<b>Commit</b><br>{v:,} deals<br>${m['commit_arr']/1e6:.1f}M ARR"
        elif s == "Onboarding":
            lbl = f"<b>Onboarding</b><br>${m['onb_arr']/1e6:.1f}M ARR"
        elif s == "Adoption":
            lbl = f"<b>Adoption</b><br>${m['adp_arr']/1e6:.1f}M ARR"
        else:
            lbl = f"<b>Expansion</b><br>${m['exp_arr']/1e6:.1f}M ARR (NRR)"

        fsize = 9 if h < 0.30 else 10 if h < 0.55 else 11
        fig.add_annotation(
            x=(x0 + x1) / 2, y=0, text=lbl, showarrow=False,
            font=dict(color="white", size=fsize),
            align="center", xanchor="center", yanchor="middle",
        )

    for a, b in RATE_PAIRS:
        xm    = (X[a] + _BT_BLK_W + X[b]) / 2
        rate  = m["rates"].get((a, b), 0.0)
        y_lbl = -(min(H[a], H[b]) + 0.09)
        label = f"{rate:.1f}% NRR" if b == "Expansion" else f"{rate:.1f}%"
        fig.add_annotation(
            x=xm, y=y_lbl, text=label, showarrow=False,
            font=dict(color=_BT_MUTED, size=9), align="center",
        )

    x_div = X[_BT_CENTER] + _BT_BLK_W / 2
    fig.add_shape(
        type="line", x0=x_div, x1=x_div,
        y0=-(_BT_MAX_H + 0.06), y1=(_BT_MAX_H + 0.04),
        line=dict(color=HAIRLINE, dash="dot", width=1.2),
    )
    fig.add_annotation(
        x=X[_BT_CENTER] - 0.1, y=_BT_MAX_H + 0.10,
        text="Pre-Sale", showarrow=False,
        font=dict(color="#ff4d8b", size=9), xanchor="right",
    )
    fig.add_annotation(
        x=X[_BT_CENTER] + _BT_BLK_W + 0.1, y=_BT_MAX_H + 0.10,
        text="Post-Sale", showarrow=False,
        font=dict(color="#1a7070", size=9), xanchor="left",
    )

    x_max = X["Expansion"] + _BT_BLK_W + 0.4
    fig.update_layout(
        title=dict(
            text=f"<b>GTM Bowtie</b>  ·  {subtitle}",
            font=dict(size=14, color=CHART_FONT),
            x=0.5, xanchor="center",
        ),
        xaxis=dict(visible=False, range=[-0.15, x_max]),
        yaxis=dict(visible=False,
                   range=[-(_BT_MAX_H + 0.22), _BT_MAX_H + 0.13]),
        plot_bgcolor=CHART_BG,
        paper_bgcolor=CHART_BG,
        font=dict(color=CHART_FONT, family="Inter, system-ui, sans-serif"),
        height=460,
        margin=dict(t=52, b=20, l=10, r=20),
        hovermode="closest",
    )
    return fig


# ── chat: summary stats + system prompt ────────────────────────────────────────
def compute_summary_stats(deal_data, agg_data):
    """Compute a compact set of summary stats for the chat advisor, based on
    whatever slice of the data is currently passed in (e.g. the filtered df)."""

    vols = compute_stage_volumes(deal_data, agg_data)
    conversion_rates = compute_conversion_rates(deal_data, agg_data)

    # Average days-in-stage by segment (Selection onward only — Awareness/
    # Education have no per-deal records)
    avg_days_in_stage = (
        deal_data.groupby(["stage_entered", "segment"], observed=True)["days_in_stage"]
        .mean().round(1).reset_index()
        .rename(columns={"stage_entered": "stage"})
        .to_dict("records")
    )

    # NRR / GRR — overall and by cohort
    post = deal_data[deal_data["stage_entered"].isin(POSTSALE)]
    nrr_grr_by_cohort = []
    for cq, grp in post.groupby("cohort_quarter"):
        base_arr = grp["deal_value"].sum()
        churn_arr = grp[grp["churned"]]["deal_value"].sum()
        exp_arr = grp["expansion_revenue"].sum()
        grr = (base_arr - churn_arr) / base_arr * 100 if base_arr else 0
        nrr = (base_arr - churn_arr + exp_arr) / base_arr * 100 if base_arr else 0
        nrr_grr_by_cohort.append({
            "cohort_quarter": cq,
            "GRR_pct": round(grr, 1),
            "NRR_pct": round(nrr, 1),
            "churn_rate_pct": round(grp["churned"].mean() * 100, 1),
        })
    nrr_grr_by_cohort.sort(key=lambda r: r["cohort_quarter"])

    base_arr = post["deal_value"].sum()
    churn_arr = post[post["churned"]]["deal_value"].sum()
    exp_arr = post["expansion_revenue"].sum()
    overall_grr = round((base_arr - churn_arr) / base_arr * 100, 1) if base_arr else 0
    overall_nrr = round((base_arr - churn_arr + exp_arr) / base_arr * 100, 1) if base_arr else 0

    # Stage velocity trend (avg days-in-stage per cohort quarter)
    velocity_by_cohort = (
        deal_data.groupby(["cohort_quarter", "stage_entered"], observed=True)["days_in_stage"]
        .mean().round(1).reset_index()
        .rename(columns={"stage_entered": "stage"})
        .to_dict("records")
    )

    # Segment performance — Selection->Commit conversion and post-sale churn rate
    segment_performance = []
    for seg in SEGMENTS:
        seg_df = deal_data[deal_data["segment"] == seg]
        sel = (seg_df["stage_entered"] == "Selection").sum()
        com = ((seg_df["stage_entered"] == "Selection") & (seg_df["stage_exited"] == "Commit")).sum()
        rate = round(com / sel * 100, 1) if sel else 0
        seg_post = seg_df[seg_df["stage_entered"].isin(POSTSALE)]
        churn_rate = round(seg_post["churned"].mean() * 100, 1) if len(seg_post) else 0
        segment_performance.append({
            "segment": seg,
            "selection_to_commit_rate_pct": rate,
            "post_sale_churn_rate_pct": churn_rate,
        })

    worst_conversion_segment = min(segment_performance, key=lambda r: r["selection_to_commit_rate_pct"])["segment"]
    worst_churn_segment = max(segment_performance, key=lambda r: r["post_sale_churn_rate_pct"])["segment"]

    return {
        "total_deal_records": int(len(deal_data)),
        "stage_volumes": {stage: int(vols[stage]) for stage in STAGE_ORDER},
        "conversion_rates": conversion_rates,
        "avg_days_in_stage": avg_days_in_stage,
        "nrr_grr_by_cohort": nrr_grr_by_cohort,
        "overall_grr_pct": overall_grr,
        "overall_nrr_pct": overall_nrr,
        "velocity_by_cohort": velocity_by_cohort,
        "segment_performance": segment_performance,
        "worst_conversion_segment": worst_conversion_segment,
        "worst_churn_segment": worst_churn_segment,
    }


def build_company_context(acv_band, segment, motion):
    def val(x):
        return x if x != "Select..." else "not provided"

    return (
        "COMPANY CONTEXT:\n"
        f"- ACV band: {val(acv_band)}\n"
        f"- Segment: {val(segment)}\n"
        f"- GTM motion: {val(motion)}"
    )


ADVISOR_PERSONA = """ROLE

You are a senior Revenue Operations advisor trained in the Winning by Design (WbD) Revenue Architecture and Bowtie framework. You diagnose B2B SaaS funnel problems the way a good doctor reads a chart: you name the specific failure, its most likely root cause, and the intervention, in that order. You are direct. You do not hedge for the sake of sounding safe. When something genuinely depends on a missing fact, you say what it depends on and ask for that one fact rather than retreating into "it depends."

You advise a human operator who decides what to act on. You recommend plays for people to run; you never imply automated action on accounts.

THE BOWTIE (your mental model)

The funnel is mirrored at the Commit knot. The LEFT bowtie is acquisition, counted in units (leads, opps, wins). The RIGHT bowtie is recurring revenue, counted in money (GRR, NRR). The eight stages:

Awareness → Education → Selection → Commit (the pinch point / Closed-Won) → Onboarding → Adoption → Renewal → Expansion.

First principle: growth comes from helping customers reach their desired impact. Two of the three growth engines (retention and expansion) live in the right bowtie, outside the traditional funnel. This drives your single most important diagnostic instinct: a declining-NRR or churn problem is almost never solved with more leads. When an operator's instinct is "we need more top-of-funnel," check whether the real leak is mid-funnel conversion, velocity, or post-sale first.

SPICED (Situation, Pain, Impact, Critical Event, Decision) is the connective tissue across stages. If Impact and Critical Event were never captured at Commit, Onboarding and Adoption have no north star and Renewal/Expansion lack proof. Weak SPICED capture upstream predicts right-bowtie leakage downstream. When you see post-sale problems with healthy acquisition, probe whether Impact was captured at the handoff.

ORDER OF OPERATIONS (follow this every time)


Validate before concluding. Watch for data-quality tells: stage definitions that don't match buyer behavior, medians that blend wildly different deal sizes, a time window shorter than the sales cycle. If something looks like a definition problem rather than a performance problem, say so first.
Find the leak by RECOVERABLE REVENUE, not the loudest stage. Rank leaks by volume × plausible lift × deal value. A 3-point lift on a high-traffic early stage usually beats a 15-point lift on a thin late stage. Don't fixate on the stage leadership asks about weekly while opportunities die two stages earlier.
Read two signals per stage: stage-to-stage conversion AND median time-in-stage. Low conversion holding across quarters is structural, not noise. A deal at 2× stage-median time is stuck.
Decompose, don't average. Push to segment by ACV band, segment, cohort, channel, or rep. Medians hide everything.
Recommend changing one thing, then measuring over a full sales cycle. Optimization is a loop, not a one-shot fix.


ANCHORING DISCIPLINE (this is what makes you credible)

Never cite a benchmark without anchoring it to ACV band, segment, and motion. The same number can be healthy or alarming depending on context (15% win rate: healthy sub-$1k, red flag over $150k; 97% SMB NRR: a median, not a crisis).

If ACV band, segment, or motion is missing from the company context, ask for it before delivering a benchmark comparison. One crisp question, not a list.

Before reacting to an MQL→SQL number, ask how the operator defines MQL. The "healthy" range swings from 5–15% (broad pool) to 35–45% (ICP-filtered). Most benchmark panic is a definition mismatch, not a real problem.

For any NRR question, decompose before diagnosing:


NRR down + GRR flat → an EXPANSION problem (customers stay, but growth within base has stalled).
NRR down + GRR also falling → a RETENTION/CHURN problem (right-bowtie Renewal).
NRR above 100% can still hide trouble: check logo churn and whether a few big accounts carry all the expansion.


BENCHMARKS (reference knowledge — always anchor, never quote blindly)

WbD Table 6.2 conversion benchmarks by ACV band (n=868, 2016–2022). Use the row matching the company's ACV band.

ACV bandCR1 AwareCR2 Lead→OppCR3 PrioritizeCR4 WinCR5 (1−disc)CR6 (1−onb churn)CR7 GRRCR8 Expansion≤ $1k5%10%65%15%90%90%90%5%≤ $5k7%12%70%17%85%92%92%10%≤ $15k8%15%80%20%81%93%95%15%≤ $50k9%18%90%25%80%94%96%20%≤ $150k10%20%95%30%78%98%97%25%> $150kn/an/a100%35%74%99%98%30%

NRR by segment (SaaS Mag, 2026, n=939): SMB (ACV <$25k) median 97%; Mid-Market ($25k–$100k) 108%; Enterprise (>$100k) 118%. Decision rule: <100% sustained = leaky bucket / PMF concern; 100–110% healthy; 110–120% strong; 120%+ premium-multiple territory. SMB ~97% is a median, not a warning.

Win rate: overall median ~21%, top performers 35%+. Practical segment targets: SMB 35%+, Mid-Market 30%+, Enterprise 25%+. Flag a win rate more than ~5 points below the ACV-appropriate band.

GRR: median ~88–92%, top quartile 94%+, below 80% is a red flag ("expansion is a band-aid on a gunshot wound").

Sales cycle by ACV: <$15k = 14–30 days; $15k–$100k = 30–90 days; >$100k = 90–180+ days; >$250k = 180–365+ days. Cross-segment median ~84 days.

Monthly logo churn by segment: SMB 3–5%; Mid-Market 1.5–3%; Enterprise 1–2%; best-in-class <1%.

Onboarding / activation: 40–60% of cancellations happen in the first 90 days. Customers who reach first value within ~14 days retain ≥80% at month 12; those who haven't by day 30 retain only 35–50%.

Adoption early-warning signals: login-frequency decline is the earliest (~60 days pre-churn); feature adoption <30% correlates with ~80% first-year churn; NPS <20 doubles churn risk. 70–80% of churned accounts showed identifiable risk 30+ days out.

Renewal: 60–70% of annual churn lands within 60 days of the renewal date. Up to ~40% of churn can be involuntary (failed payments) and is largely preventable. Annual contracts churn 30–40% less than monthly.

PLAYS (match the leak to the fix)


Low Awareness→Education (lead quality): tighten ICP and channel mix; reweight lead scoring toward high-intent signals (pricing/demo) over content downloads. Fewer, better MQLs usually beats more.
Low Education→Selection (MQL→SQL): speed-to-lead is the highest-leverage lever (contacting within the hour dramatically raises qualification odds). Align marketing and sales on the SQL definition.
Low Selection→Commit (win rate): enforce Critical Event discovery (the SPICED "CE"), a real qualification gate, value-based not feature-based demos, and a clear next step every meeting. Multi-thread: 3+ engaged stakeholders close far higher than single-threaded deals.
Slow Onboarding: define ONE validated activation event and shorten time-to-it relentlessly. Structured onboarding meaningfully lifts first-year retention.
Low Adoption: weekly health scoring (usage, feature breadth, engagement) with proactive check-ins at days 7/30/60/90.
Churn at Renewal: open renewal 90 days out; T-60 value-review quantifying realized ROI; T-30 bundle renewal + expansion; fix involuntary churn (dunning, card updates).
Expansion: run Land → Adopt → Prove → Expand; most teams skip "Prove" and pitch too early. Reliable triggers: crossing ~80% of seat/tier capacity, a new team adopting, a funding round, deep non-core feature use, a QBR where ROI is quantified.


MOTION-SPECIFIC FRAMING


PLG: diagnose activation rate and PQL conversion, not MQL→SQL. The prospect enters through the product. Watch the self-serve → sales-assist handoff; measure activation at the account/team level. PQLs convert ~2–3× MQLs.
Sales-led: classic left-bowtie diagnosis (MQL→SQL→SAL→Win), multi-threading, SPICED, cycle compression. Most spend sits in S&M; CAC payback of 12–24 months is structural, not a problem.
Hybrid / Product-Led Sales: instrument the PQL→sales-engaged handoff explicitly; make sure comp rewards expansion, not just land. Map ACV tier to motion (sub-$5k deals have to be PLG economically).


HONESTY AND PROVENANCE (do not skip)


If you don't have a sourced number for something, say so plainly. Do not invent figures. Never fabricate gated benchmark aggregates (e.g., BenchSights) or region-specific EMEA numbers — none are publicly published, so say that rather than guess.
WbD publishes conversion benchmarks but NOT time-in-stage durations; those come from third parties. Keep that straight if asked about sourcing.
Distinguish a structural trend (holds across quarters) from a one-quarter blip, and say which you think you're looking at.
When the data is too thin to support a confident diagnosis, name the one additional cut or field that would unlock it.


OUTPUT FORMAT

Default to a tight, structured answer:

Leak: the specific stage/metric that's off, with the actual number vs. the anchored benchmark.
Likely cause: the one or two most probable root causes, given the context.
Play: the single highest-leverage intervention to run first.
Caveat: one honest caveat or the one fact you'd want to confirm.

Keep it to a few sentences per part. Lead with the biggest recoverable leak, not a stage-by-stage tour. Expand into a fuller multi-stage breakdown only when the operator asks for it. Match the operator's altitude: if they ask a narrow question, answer it narrowly. No filler, no preamble, no restating their question back to them."""


def build_system_prompt(stats, company_context):
    return (
        ADVISOR_PERSONA
        + "\n\n"
        + company_context
        + "\n\n"
        + "DATA SNAPSHOT (JSON):\n"
        + json.dumps(stats, indent=2, default=str)
    )


def get_anthropic_api_key():
    try:
        return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        return os.environ.get("ANTHROPIC_API_KEY")


# ── sidebar: company profile ────────────────────────────────────────────────
st.sidebar.header("Company Profile")
st.sidebar.caption("Used by the diagnostic advisor to pick the right benchmarks.")

acv_band = st.sidebar.selectbox(
    "ACV band",
    options=["Select...", "≤ $1k", "≤ $5k", "≤ $15k", "≤ $50k", "≤ $150k", "> $150k"],
)
company_segment = st.sidebar.selectbox(
    "Segment",
    options=["Select...", "SMB", "Mid-Market", "Enterprise"],
)
gtm_motion = st.sidebar.selectbox(
    "GTM motion",
    options=["Select...", "Sales-led", "PLG", "Hybrid"],
)

st.sidebar.markdown("---")

# ── sidebar filters ───────────────────────────────────────────────────────────
st.sidebar.header("Filters")

segments = st.sidebar.multiselect(
    "Segment", options=SEGMENTS, default=SEGMENTS,
)
cohorts = sorted(set(df["cohort_quarter"]) | set(agg_df["cohort_quarter"]))
selected_cohorts = st.sidebar.multiselect(
    "Cohort Quarter", options=cohorts, default=cohorts,
)
reps = st.sidebar.multiselect(
    "Rep", options=sorted(df["rep_name"].unique()), default=sorted(df["rep_name"].unique()),
)

fdf = df[
    df["segment"].isin(segments) &
    df["cohort_quarter"].isin(selected_cohorts) &
    df["rep_name"].isin(reps)
].copy()

# Awareness/Education aggregate rows have no segment or rep, so only the
# cohort filter applies to them.
fagg = agg_df[
    agg_df["cohort_quarter"].isin(selected_cohorts) &
    agg_df["segment"].isin(segments)
].copy()

st.sidebar.markdown("---")
st.sidebar.metric("Filtered Deal Records", f"{len(fdf):,}")

# ── header ────────────────────────────────────────────────────────────────────
st.title("GTM Health Diagnostic")
st.markdown(
    f"Showing **{len(fdf):,}** of {len(df):,} deal records (Selection → Expansion) · "
    f"{len(segments)} segment(s) · {len(selected_cohorts)} cohort(s)"
)

tabs = st.tabs([
    "Bowtie Funnel",
    "Conversion Rates",
    "Days in Stage",
    "NRR / GRR by Cohort",
    "Stage Velocity",
])

# ═════════════════════════════════════════════════════════════════════════════
# TAB 1 — Bowtie Funnel
# ═════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader("Bowtie Funnel — Volume by Stage")

    vols = compute_stage_volumes(fdf, fagg)

    # KPI row
    col1, col2, col3, col4 = st.columns(4)
    awareness = vols["Awareness"]
    committed = vols["Commit"]
    overall_conv = (committed / awareness * 100) if awareness else 0

    total_arr_committed = fdf[fdf["stage_entered"].isin(POSTSALE)]["deal_value"].sum()
    total_exp = fdf["expansion_revenue"].sum()
    churn_arr = fdf[fdf["churned"]]["deal_value"].sum()
    gross_retention = 1 - churn_arr / total_arr_committed if total_arr_committed else 0
    nrr = (total_arr_committed + total_exp - churn_arr) / total_arr_committed if total_arr_committed else 0

    col1.metric("Awareness Leads", f"{awareness:,}")
    col2.metric("Awareness → Commit", f"{overall_conv:.2f}%")
    col3.metric("GRR", f"{gross_retention*100:.1f}%")
    col4.metric("NRR", f"{nrr*100:.1f}%")

    # ── cohort dropdown ──────────────────────────────────────────────────────
    bt_cohorts = ["All cohorts"] + sorted(
        set(fdf["cohort_quarter"]) | set(fagg["cohort_quarter"])
    )
    bt_cohort = st.selectbox(
        "Cohort", options=bt_cohorts, key="bowtie_cohort",
        label_visibility="collapsed",
        help="All cohorts summed, or select a single quarter.",
    )
    if bt_cohort == "All cohorts":
        bt_deal, bt_agg = fdf, fagg
    else:
        bt_deal = fdf[fdf["cohort_quarter"] == bt_cohort]
        bt_agg  = fagg[fagg["cohort_quarter"] == bt_cohort]

    bt_m = _compute_bowtie(bt_deal, bt_agg)
    subtitle_parts = [bt_cohort]
    if set(segments) != set(SEGMENTS):
        subtitle_parts.append(", ".join(sorted(segments)))
    bt_subtitle = "  ·  ".join(subtitle_parts)
    st.plotly_chart(_build_bowtie_fig(bt_m, bt_subtitle), use_container_width=True)
    st.caption(
        "Block height is log-scaled so all stages are visible. "
        "Left: deal volume (Awareness -> Commit). "
        "Right: ARR -- Onboarding (committed), Adoption (GRR after churn), "
        "Expansion (NRR including expansion revenue)."
    )

    st.markdown("#### Top-of-Funnel Volume by Segment (Awareness → Selection)")
    agg_seg = (
        fagg.groupby(["stage_entered", "segment"])["count_entered"]
        .sum().reset_index(name="count")
    )
    sel_seg = (
        fdf[fdf["stage_entered"] == "Selection"]
        .groupby("segment", observed=True).size()
        .reset_index(name="count")
    )
    sel_seg["stage_entered"] = "Selection"
    tof_seg = pd.concat([
        agg_seg[["stage_entered", "segment", "count"]],
        sel_seg[["stage_entered", "segment", "count"]],
    ], ignore_index=True)
    fig_tof = px.bar(
        tof_seg, x="stage_entered", y="count", color="segment",
        color_discrete_map=SEGMENT_COLORS,
        category_orders={"stage_entered": ["Awareness", "Education", "Selection"]},
        labels={"count": "Volume", "stage_entered": "Stage"},
        log_y=True,
    )
    fig_tof.update_layout(
        plot_bgcolor=CHART_BG, paper_bgcolor=CHART_BG, font_color=CHART_FONT,
        height=270, margin=dict(t=10, b=20),
    )
    st.plotly_chart(fig_tof, use_container_width=True)

    st.markdown("#### Pipeline ARR by Segment (Commit → Expansion)")
    _commit_plus = ["Commit", "Onboarding", "Adoption", "Renewal", "Expansion"]
    arr_seg = (
        fdf[fdf["stage_entered"].isin(_commit_plus)]
        .groupby(["stage_entered", "segment"], observed=True)["deal_value"]
        .sum().div(1e6).round(2)
        .reset_index(name="arr_m")
    )
    fig_arr = px.bar(
        arr_seg, x="stage_entered", y="arr_m", color="segment",
        color_discrete_map=SEGMENT_COLORS,
        category_orders={"stage_entered": _commit_plus},
        labels={"arr_m": "ARR ($M)", "stage_entered": "Stage"},
    )
    fig_arr.update_layout(
        plot_bgcolor=CHART_BG, paper_bgcolor=CHART_BG, font_color=CHART_FONT,
        height=280, margin=dict(t=10, b=20),
    )
    st.plotly_chart(fig_arr, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — Conversion Rates
# ═════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("Stage-to-Stage Conversion Rates")
    st.caption(
        "Rate = deals that EXITED into the next stage ÷ deals that ENTERED "
        "this stage, per the cohort-flow model."
    )

    rates = compute_conversion_rates(fdf, fagg)
    transitions = [f"{r['from']} → {r['to']}" for r in rates]
    conv_rates  = [r["rate_pct"] for r in rates]

    colors = [PRESALE_COLOR if i < 3 else POSTSALE_COLOR for i in range(len(transitions))]

    fig_conv = go.Figure(go.Bar(
        x=transitions,
        y=conv_rates,
        marker_color=colors,
        text=[f"{v:.1f}%" for v in conv_rates],
        textposition="outside",
        hovertemplate="%{x}<br>Conversion: %{y:.1f}%<extra></extra>",
    ))
    fig_conv.add_hline(y=50, line_dash="dot", line_color=HAIRLINE,
                       annotation_text="50% benchmark", annotation_position="top right")
    fig_conv.update_layout(
        yaxis=dict(title="Conversion Rate (%)", range=[0, max(conv_rates) * 1.25]),
        xaxis_tickangle=-30,
        plot_bgcolor=CHART_BG, paper_bgcolor=CHART_BG, font_color=CHART_FONT,
        height=420, margin=dict(t=20, b=80),
    )
    st.plotly_chart(fig_conv, use_container_width=True)

    # Table
    conv_df = pd.DataFrame({
        "Transition": transitions,
        "Entered": [r["entered"] for r in rates],
        "Exited to next": [r["exited"] for r in rates],
        "Rate": [f"{r['rate_pct']:.1f}%" for r in rates],
    })
    st.dataframe(conv_df, use_container_width=True, hide_index=True)

    # Conversion by segment (Selection -> Commit is the first transition
    # where deal-level segment data is available)
    st.markdown("#### Selection → Commit Conversion by Segment")
    seg_conv_rows = []
    for seg in SEGMENTS:
        seg_df = fdf[fdf["segment"] == seg]
        sel = (seg_df["stage_entered"] == "Selection").sum()
        com = ((seg_df["stage_entered"] == "Selection") & (seg_df["stage_exited"] == "Commit")).sum()
        rate = com / sel * 100 if sel else 0
        seg_conv_rows.append({"Segment": seg, "Selection": sel, "Commit": com, "Rate": f"{rate:.1f}%"})
    st.dataframe(pd.DataFrame(seg_conv_rows), use_container_width=True, hide_index=True)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 3 — Average Days in Stage
# ═════════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("Average Days in Stage by Segment")
    st.caption("Awareness/Education: avg days per segment from aggregate rows. Selection → Expansion: per-deal records.")

    agg_days = (
        fagg.groupby(["stage_entered", "segment"])["days_in_stage"]
        .mean().round(1).reset_index()
    )
    deal_days = (
        fdf.groupby(["stage_entered", "segment"], observed=True)["days_in_stage"]
        .mean().round(1).reset_index()
    )
    days_df = pd.concat([agg_days, deal_days], ignore_index=True)

    fig_days = px.bar(
        days_df, x="stage_entered", y="days_in_stage", color="segment",
        barmode="group",
        color_discrete_map=SEGMENT_COLORS,
        category_orders={"stage_entered": STAGE_ORDER},
        labels={"days_in_stage": "Avg Days", "stage_entered": "Stage"},
        text_auto=".0f",
    )
    fig_days.update_traces(textposition="outside")
    fig_days.update_layout(
        plot_bgcolor=CHART_BG, paper_bgcolor=CHART_BG, font_color=CHART_FONT,
        height=420, margin=dict(t=20, b=20), legend_title="Segment",
    )
    st.plotly_chart(fig_days, use_container_width=True)

    # Heatmap — stage × segment
    st.markdown("#### Heatmap: Avg Days (Stage × Segment)")
    heat = days_df.pivot(index="segment", columns="stage_entered", values="days_in_stage")
    heat = heat.reindex(columns=STAGE_ORDER)

    fig_heat = px.imshow(
        heat,
        text_auto=".0f",
        color_continuous_scale=["#f5f0e0", "#b8a4ed", "#1a3a3a"],
        labels=dict(color="Avg Days"),
        aspect="auto",
    )
    fig_heat.update_layout(
        plot_bgcolor=CHART_BG, paper_bgcolor=CHART_BG, font_color=CHART_FONT,
        height=260, margin=dict(t=10, b=10),
        xaxis_title="", yaxis_title="",
    )
    st.plotly_chart(fig_heat, use_container_width=True)

    # Distribution violin
    st.markdown("#### Days-in-Stage Distribution")
    fig_viol = px.violin(
        fdf, x="stage_entered", y="days_in_stage", color="segment",
        color_discrete_map=SEGMENT_COLORS,
        category_orders={"stage_entered": DEAL_STAGES},
        box=True, points=False,
        labels={"days_in_stage": "Days in Stage", "stage_entered": ""},
    )
    fig_viol.update_layout(
        plot_bgcolor=CHART_BG, paper_bgcolor=CHART_BG, font_color=CHART_FONT,
        height=350, margin=dict(t=10, b=10),
    )
    st.plotly_chart(fig_viol, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 4 — NRR / GRR by Cohort
# ═════════════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("NRR & GRR by Cohort Quarter")

    post = fdf[fdf["stage_entered"].isin(POSTSALE)].copy()

    cohort_metrics = []
    for cq, grp in post.groupby("cohort_quarter"):
        base_arr  = grp["deal_value"].sum()
        churn_arr = grp[grp["churned"]]["deal_value"].sum()
        exp_arr   = grp["expansion_revenue"].sum()
        grr = (base_arr - churn_arr) / base_arr * 100 if base_arr else 0
        nrr = (base_arr - churn_arr + exp_arr) / base_arr * 100 if base_arr else 0
        cohort_metrics.append({
            "cohort_quarter": cq,
            "base_arr": base_arr,
            "churn_arr": churn_arr,
            "expansion_arr": exp_arr,
            "GRR": round(grr, 1),
            "NRR": round(nrr, 1),
            "churned_pct": round(grp["churned"].mean() * 100, 1),
        })

    cm = pd.DataFrame(cohort_metrics).sort_values("cohort_quarter")

    fig_nrr = go.Figure()
    fig_nrr.add_trace(go.Bar(
        x=cm["cohort_quarter"], y=cm["GRR"],
        name="GRR", marker_color=MM_COLOR,
        hovertemplate="%{x}<br>GRR: %{y:.1f}%<extra></extra>",
    ))
    fig_nrr.add_trace(go.Scatter(
        x=cm["cohort_quarter"], y=cm["NRR"],
        name="NRR", mode="lines+markers",
        line=dict(color=POSTSALE_COLOR, width=3),
        marker=dict(size=8),
        hovertemplate="%{x}<br>NRR: %{y:.1f}%<extra></extra>",
    ))
    fig_nrr.add_hline(y=100, line_dash="dash", line_color=HAIRLINE,
                      annotation_text="100%", annotation_position="top left")
    fig_nrr.update_layout(
        yaxis=dict(title="Rate (%)", range=[80, max(cm["NRR"].max(), 115) + 5]),
        xaxis_tickangle=-30,
        plot_bgcolor=CHART_BG, paper_bgcolor=CHART_BG, font_color=CHART_FONT,
        height=400, margin=dict(t=20, b=80), legend=dict(x=0.01, y=0.99),
    )
    st.plotly_chart(fig_nrr, use_container_width=True)

    # ARR waterfall by cohort
    st.markdown("#### ARR Waterfall: Base vs Churn vs Expansion")
    fig_wf = go.Figure()
    fig_wf.add_trace(go.Bar(
        x=cm["cohort_quarter"], y=cm["base_arr"] / 1e6,
        name="Base ARR", marker_color=MM_COLOR,
    ))
    fig_wf.add_trace(go.Bar(
        x=cm["cohort_quarter"], y=-cm["churn_arr"] / 1e6,
        name="Churned ARR", marker_color="#ff6b5a",
    ))
    fig_wf.add_trace(go.Bar(
        x=cm["cohort_quarter"], y=cm["expansion_arr"] / 1e6,
        name="Expansion ARR", marker_color=POSTSALE_COLOR,
    ))
    fig_wf.update_layout(
        barmode="relative",
        yaxis_title="ARR ($M)",
        xaxis_tickangle=-30,
        plot_bgcolor=CHART_BG, paper_bgcolor=CHART_BG, font_color=CHART_FONT,
        height=350, margin=dict(t=10, b=80),
    )
    st.plotly_chart(fig_wf, use_container_width=True)

    # Table
    display_cm = cm[["cohort_quarter", "GRR", "NRR", "churned_pct"]].copy()
    display_cm.columns = ["Cohort", "GRR (%)", "NRR (%)", "Churn Rate (%)"]
    st.dataframe(display_cm, use_container_width=True, hide_index=True)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 5 — Stage Velocity Trends
# ═════════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.subheader("Stage Velocity Trends Over Time")
    st.caption("Avg days-in-stage per cohort quarter — lower is faster. Selection → Expansion only.")

    agg_vel = (
        fagg.groupby(["cohort_quarter", "stage_entered"])["days_in_stage"]
        .mean().round(1).reset_index()
        .rename(columns={"stage_entered": "stage"})
    )
    deal_vel = (
        fdf.groupby(["cohort_quarter", "stage_entered"], observed=True)["days_in_stage"]
        .mean().round(1).reset_index()
        .rename(columns={"stage_entered": "stage"})
    )
    velocity = pd.concat([agg_vel, deal_vel], ignore_index=True)

    focus_stages = st.multiselect(
        "Select stages to display",
        options=STAGE_ORDER,
        default=["Awareness", "Selection", "Commit", "Onboarding", "Adoption"],
    )

    vel_filtered = velocity[velocity["stage"].isin(focus_stages)]

    fig_vel = px.line(
        vel_filtered, x="cohort_quarter", y="days_in_stage",
        color="stage", markers=True,
        labels={"days_in_stage": "Avg Days", "cohort_quarter": "Cohort Quarter", "stage": "Stage"},
        category_orders={"stage": DEAL_STAGES},
    )
    fig_vel.update_traces(line_width=2.5, marker_size=7)
    fig_vel.update_layout(
        xaxis_tickangle=-30,
        plot_bgcolor=CHART_BG, paper_bgcolor=CHART_BG, font_color=CHART_FONT,
        height=400, margin=dict(t=10, b=80),
    )
    st.plotly_chart(fig_vel, use_container_width=True)

    # Volume entering each stage per quarter — combines the Awareness/Education
    # aggregate counts with deal-level counts for Selection onward
    st.markdown("#### Volume Entering Each Stage by Quarter")
    deal_vol = (
        fdf.groupby(["cohort_quarter", "stage_entered"], observed=True)["deal_id"]
        .count().reset_index(name="count")
        .rename(columns={"stage_entered": "stage"})
    )
    agg_vol = (
        fagg.groupby(["cohort_quarter", "stage_entered"])["count_entered"]
        .sum().reset_index()
        .rename(columns={"stage_entered": "stage", "count_entered": "count"})
    )
    vol_trend = pd.concat([agg_vol, deal_vol], ignore_index=True)

    focus_vol = st.multiselect(
        "Stages for volume trend",
        options=STAGE_ORDER,
        default=["Awareness", "Commit", "Expansion"],
        key="vol_stages",
    )
    fig_vol = px.line(
        vol_trend[vol_trend["stage"].isin(focus_vol)],
        x="cohort_quarter", y="count", color="stage", markers=True,
        labels={"count": "Volume", "cohort_quarter": "Cohort Quarter"},
        category_orders={"stage": STAGE_ORDER},
    )
    fig_vol.update_traces(line_width=2.5, marker_size=7)
    fig_vol.update_layout(
        xaxis_tickangle=-30,
        yaxis_type="log",
        plot_bgcolor=CHART_BG, paper_bgcolor=CHART_BG, font_color=CHART_FONT,
        height=350, margin=dict(t=10, b=80),
    )
    st.plotly_chart(fig_vol, use_container_width=True)
    st.caption("Volume is shown on a log scale to make sense of Awareness/Education alongside the much smaller deal-level stages.")

    # Velocity heatmap: stage × quarter
    st.markdown("#### Velocity Heatmap: Avg Days (Stage × Cohort Quarter)")
    vel_heat = velocity.pivot(index="stage", columns="cohort_quarter", values="days_in_stage")
    vel_heat = vel_heat.reindex(STAGE_ORDER)

    fig_vh = px.imshow(
        vel_heat,
        text_auto=".0f",
        color_continuous_scale=["#1a3a3a", "#e8b94a", "#ff4d8b"],
        labels=dict(color="Avg Days"),
        aspect="auto",
    )
    fig_vh.update_layout(
        plot_bgcolor=CHART_BG, paper_bgcolor=CHART_BG, font_color=CHART_FONT,
        height=380, margin=dict(t=10, b=10),
        xaxis_title="", yaxis_title="",
        xaxis_tickangle=-30,
    )
    st.plotly_chart(fig_vh, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════════
# RevOps Diagnostic Chat
# ═════════════════════════════════════════════════════════════════════════════
st.markdown("---")
st.header("Ask the RevOps Diagnostic Advisor")
st.caption(
    "Ask about conversion rates, stage velocity, NRR/GRR, or which segments are "
    "underperforming. Answers are grounded in the data currently selected in the "
    "sidebar filters."
)

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("e.g. Where are deals getting stuck, and what should we fix first?"):
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    api_key = get_anthropic_api_key()
    with st.chat_message("assistant"):
        if not api_key:
            st.error(
                "No Anthropic API key found. Create `.streamlit/secrets.toml` in the "
                "project folder with a line like:\n\n"
                '`ANTHROPIC_API_KEY = "sk-ant-..."`\n\n'
                "then restart the app."
            )
        else:
            try:
                client = anthropic.Anthropic(api_key=api_key)
                stats = compute_summary_stats(fdf, fagg)
                company_context = build_company_context(acv_band, company_segment, gtm_motion)
                system_prompt = build_system_prompt(stats, company_context)
                with st.spinner("Analyzing the funnel..."):
                    response = client.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=4096,
                        thinking={"type": "adaptive"},
                        system=system_prompt,
                        messages=[
                            {"role": m["role"], "content": m["content"]}
                            for m in st.session_state.chat_history
                        ],
                    )
                reply = "".join(
                    block.text for block in response.content if block.type == "text"
                )
                st.markdown(reply)
                st.session_state.chat_history.append({"role": "assistant", "content": reply})
            except anthropic.AuthenticationError:
                st.error("Invalid Anthropic API key — check `.streamlit/secrets.toml`.")
            except anthropic.RateLimitError:
                st.error("Rate limit reached — please wait a moment and try again.")
            except anthropic.APIStatusError as e:
                st.error(f"Anthropic API error: {e}")
