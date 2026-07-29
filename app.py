import os

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import anthropic

from advisor import (
    TOOL_SCHEMAS,
    build_company_context,
    build_system_prompt,
    execute_tool,
    run_advisor_turn,
)
from charts import (
    CHART_BG,
    CHART_FONT,
    ENT_COLOR,
    HAIRLINE,
    MM_COLOR,
    PRESALE_COLOR,
    POSTSALE_COLOR,
    SEGMENT_COLORS,
    SMB_COLOR,
    build_bowtie_fig,
)
from data.loader import load_data as _load_data
from metrics import (
    DEAL_STAGES,
    MIN_ABS_DROP_PP,
    MIN_COHORTS_FOR_ZSCORE,
    MOTIONS,
    POSTSALE,
    SEGMENTS,
    STAGE_ORDER,
    ZSCORE_THRESHOLD,
    compute_bowtie,
    compute_conversion_anomalies,
    compute_conversion_rates,
    compute_headline_snapshot,
    compute_stage_volumes,
    deal_snapshot,
)

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

# The deployed demo runs on a personal Anthropic key, so each browser session
# gets a fixed question budget. Streamlit session state resets on refresh, which
# makes this a courtesy limit rather than a security control — it stops a casual
# loop, not a determined one.
MAX_ADVISOR_MESSAGES = 12

# Author — surfaced in the sidebar and page footer.
AUTHOR_NAME = "Tom Norton"
AUTHOR_LINKEDIN = "https://www.linkedin.com/in/tom-p-norton/"
AUTHOR_REPO = "https://github.com/tom-norton/gtm-health-diagnostic"

# ── data ─────────────────────────────────────────────────────────────────────
load_data = st.cache_data(_load_data)
agg_df, df = load_data()


def get_anthropic_api_key():
    try:
        return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        return os.environ.get("ANTHROPIC_API_KEY")


# ── sidebar: company profile ────────────────────────────────────────────────
st.sidebar.header("Company Profile")
st.sidebar.caption("Used by the diagnostic advisor to pick the right benchmarks.")

# The bands are the published Winning by Design Table 6.2 rows, which are
# denominated in USD. The dataset itself is in EUR — the advisor is told about
# the mismatch rather than us silently converting a sourced benchmark.
acv_band = st.sidebar.selectbox(
    "ACV band (WbD benchmark row, USD)",
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
motions = st.sidebar.multiselect(
    "Motion", options=MOTIONS, default=MOTIONS,
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
    df["motion"].isin(motions) &
    df["cohort_quarter"].isin(selected_cohorts) &
    df["rep_name"].isin(reps)
].copy()

# Awareness/Education aggregate rows have no segment, motion or rep, so only
# the cohort + segment filters apply to them (motion doesn't split top-of-
# funnel volume — see MOTIONS comment above).
fagg = agg_df[
    agg_df["cohort_quarter"].isin(selected_cohorts) &
    agg_df["segment"].isin(segments)
].copy()

st.sidebar.markdown("---")
st.sidebar.metric("Filtered Distinct Deals", f"{fdf['deal_id'].nunique():,}")

st.sidebar.markdown("---")
st.sidebar.markdown(
    f"Built by **{AUTHOR_NAME}**  \n"
    f"[LinkedIn]({AUTHOR_LINKEDIN}) · [Source]({AUTHOR_REPO})"
)

# ── header ────────────────────────────────────────────────────────────────────
st.title("GTM Health Diagnostic")
st.markdown(
    f"Showing **{fdf['deal_id'].nunique():,}** of {df['deal_id'].nunique():,} distinct deals "
    f"(Selection → Expansion) · {len(segments)} segment(s) · {len(motions)} motion(s) · "
    f"{len(selected_cohorts)} cohort(s)"
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

    # Deduped to one row per deal: a deal that reached Expansion has a row
    # for every postsale stage it passed through, so summing deal_value over
    # the raw rows would count its ARR once per stage instead of once.
    kpi_post = deal_snapshot(fdf)
    kpi_post = kpi_post[kpi_post["stage_entered"].isin(POSTSALE)]
    total_arr_committed = kpi_post["deal_value"].sum()
    total_exp = kpi_post["expansion_revenue"].sum()
    churn_arr = kpi_post[kpi_post["churned"]]["deal_value"].sum()
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

    bt_m = compute_bowtie(bt_deal, bt_agg)
    subtitle_parts = [bt_cohort]
    if set(segments) != set(SEGMENTS):
        subtitle_parts.append(", ".join(sorted(segments)))
    bt_subtitle = "  ·  ".join(subtitle_parts)
    st.plotly_chart(build_bowtie_fig(bt_m, bt_subtitle), use_container_width=True)
    st.caption(
        "Block height is log-scaled so all stages are visible. "
        "Left: deal volume (Awareness → Commit). "
        "Right: ARR across Onboarding, Adoption, Renewal and Expansion, with "
        "Expansion including expansion revenue (NRR). Every percentage is a "
        "stage-to-stage conversion rate on the same exits ÷ entries basis as "
        "the Conversion Rates tab."
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
        labels={"arr_m": "ARR (€M)", "stage_entered": "Stage"},
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

    # ── anomaly flags ────────────────────────────────────────────────────────
    st.markdown("#### Conversion Anomalies")
    st.caption(
        f"A quarter is flagged only when it clears two tests: at least "
        f"{abs(ZSCORE_THRESHOLD)}σ below that transition's own mean across cohorts, "
        f"**and** at least {MIN_ABS_DROP_PP:.0f} percentage points below it. The "
        f"second test matters — where a stage is very stable its standard deviation "
        f"is tiny, so a z-score alone flags fractions of a point as outliers. "
        f"Scoring is per transition, so stages with different healthy ranges aren't "
        f"compared against each other, and transitions with fewer than "
        f"{MIN_COHORTS_FOR_ZSCORE} quarters of history are left unscored."
    )

    anomalies = compute_conversion_anomalies(fdf, fagg)
    flagged = [a for a in anomalies if a["is_anomaly"]]

    if not anomalies:
        st.info(
            "Not enough cohort history in the current filter to score anomalies. "
            f"Each transition needs at least {MIN_COHORTS_FOR_ZSCORE} quarters."
        )
    elif not flagged:
        w = anomalies[0]
        st.success(
            f"No stage cleared both tests in any quarter. The largest single drop "
            f"was {w['transition']} in {w['cohort_quarter']}: {w['rate_pct']:.1f}% "
            f"against a {w['mean_pct']:.1f}% mean — {w['drop_pp']:.1f} points, "
            f"{w['z_score']:+.2f}σ. Statistically an outlier, but too small a move "
            f"to act on."
        )
    else:
        for a in flagged:
            st.error(
                f"**{a['transition']}** — {a['cohort_quarter']} converted at "
                f"**{a['rate_pct']:.1f}%** against a {a['mean_pct']:.1f}% mean: "
                f"down {a['drop_pp']:.1f} points ({a['z_score']:+.2f}σ) on "
                f"{a['entered']:,} deals entered."
            )

    if anomalies:
        anom_df = pd.DataFrame(anomalies)[
            ["transition", "cohort_quarter", "rate_pct", "mean_pct", "drop_pp",
             "z_score", "entered", "is_anomaly"]
        ]
        anom_df.columns = ["Transition", "Cohort", "Rate (%)", "Mean (%)",
                           "Drop (pp)", "Z-score", "Entered", "Flagged"]
        with st.expander("All scored quarters (largest drop first)"):
            st.dataframe(anom_df, use_container_width=True, hide_index=True)

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

    # Deduped to one row per deal — see deal_snapshot's docstring. Grouping
    # the raw multi-row log by cohort here would still double/triple-count
    # ARR within a cohort (cohort_quarter is fixed per deal, so all of a
    # deal's postsale rows land in the same group).
    post = deal_snapshot(fdf)
    post = post[post["stage_entered"].isin(POSTSALE)].copy()

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
        yaxis_title="ARR (€M)",
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
    "sidebar filters, plus live tool calls for anything not in the headline snapshot."
)

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

asked = sum(1 for m in st.session_state.chat_history if m["role"] == "user")
remaining = MAX_ADVISOR_MESSAGES - asked

if remaining <= 0:
    st.info(
        f"You've used all {MAX_ADVISOR_MESSAGES} advisor questions for this session. "
        "This is a personal-portfolio demo running on my own API key, so each "
        "visitor gets a fixed budget. Refresh the page to start a new session, or "
        "run it locally with your own key — see the README."
    )
    st.chat_input("Session question limit reached", disabled=True)
    prompt = None
else:
    if remaining <= 3:
        st.caption(f"{remaining} of {MAX_ADVISOR_MESSAGES} questions left this session.")
    prompt = st.chat_input("e.g. Where are deals getting stuck, and what should we fix first?")

if prompt:
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
                headline = compute_headline_snapshot(fdf, fagg)
                company_context = build_company_context(acv_band, company_segment, gtm_motion)
                system_prompt = build_system_prompt(headline, company_context)

                def tool_dispatch(name, tool_input, _fdf=fdf, _fagg=fagg):
                    return execute_tool(name, tool_input, _fdf, _fagg)

                with st.spinner("Analyzing the funnel..."):
                    reply, _ = run_advisor_turn(
                        client=client,
                        model="claude-sonnet-4-6",
                        system_prompt=system_prompt,
                        tools=TOOL_SCHEMAS,
                        tool_dispatch=tool_dispatch,
                        messages=[
                            {"role": m["role"], "content": m["content"]}
                            for m in st.session_state.chat_history
                        ],
                    )
                st.markdown(reply)
                st.session_state.chat_history.append({"role": "assistant", "content": reply})
            except anthropic.AuthenticationError:
                st.error("Invalid Anthropic API key — check `.streamlit/secrets.toml`.")
            except anthropic.RateLimitError:
                st.error("Rate limit reached — please wait a moment and try again.")
            except anthropic.APIStatusError as e:
                st.error(f"Anthropic API error: {e}")


# ── footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    f"Built by [{AUTHOR_NAME}]({AUTHOR_LINKEDIN}) · "
    f"[Source and methodology notes]({AUTHOR_REPO}) · "
    "Figures are EUR. Dataset is synthetic; Winning by Design benchmarks are "
    "sourced and published in USD."
)
