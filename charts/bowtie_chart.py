"""The bowtie diagram: eight blocks, log-scaled by volume/ARR, with
conversion-rate labels between each pair. The only chart complex enough to
warrant its own module -- the simpler per-tab charts in app.py build their
Plotly figures inline."""
import numpy as np
import plotly.graph_objects as go

from metrics.bowtie import BT_CENTER, BT_LEFT, BT_STAGES

from .palette import CHART_BG, CHART_FONT, HAIRLINE

_BT_COLORS = {
    "Awareness":  "#ff4d8b",   # brand-pink
    "Education":  "#e8457e",
    "Selection":  "#cc3b70",
    "Commit":     "#1a3a3a",   # brand-teal
    "Onboarding": "#1a4a4a",
    "Adoption":   "#1a5f5f",
    "Renewal":    "#1a6868",
    "Expansion":  "#1a7070",
}
_BT_BLK_W = 1.5
_BT_GAP   = 0.40
_BT_MAX_H = 1.0
_BT_MUTED = "#9a9a9a"   # muted-soft


def _log_h(vol, ref, max_h=_BT_MAX_H):
    """Log-normalised half-height so all stages remain visible."""
    if ref <= 0 or vol <= 0:
        return max_h * 0.04
    return np.log1p(vol) / np.log1p(ref) * max_h


def build_bowtie_fig(m, subtitle="All Cohorts"):
    ref = m["vols"].get("Awareness", 1)
    avg = m["avg_val"]

    eff = {
        "Awareness":  m["vols"].get("Awareness", 0),
        "Education":  m["vols"].get("Education", 0),
        "Selection":  m["vols"].get("Selection", 0),
        "Commit":     m["vols"].get("Commit", 0),
        "Onboarding": m["onb_count"],
        "Adoption":   m["adp_count"],
        "Renewal":    m["ren_count"],
        "Expansion":  int(m["exp_arr"] / avg) if avg else 0,
    }
    H = {s: _log_h(eff.get(s, 0), ref) for s in BT_STAGES}

    X = {}; x = 0.0
    for s in BT_STAGES:
        X[s] = x; x += _BT_BLK_W + _BT_GAP

    RATE_PAIRS = list(zip(BT_STAGES, BT_STAGES[1:]))

    fig = go.Figure()

    for i, s in enumerate(BT_STAGES[:-1]):
        nxt = BT_STAGES[i + 1]
        x0, x1 = X[s] + _BT_BLK_W, X[nxt]
        h0, h1 = H[s], H[nxt]
        fig.add_trace(go.Scatter(
            x=[x0, x1, x1, x0, x0], y=[h0, h1, -h1, -h0, h0],
            fill="toself", fillcolor=_BT_COLORS[s], opacity=0.28,
            line=dict(width=0), mode="lines",
            showlegend=False, hoverinfo="skip",
        ))

    for s in BT_STAGES:
        x0, x1 = X[s], X[s] + _BT_BLK_W
        h   = H[s]
        idx = BT_STAGES.index(s)
        v   = m["vols"].get(s, 0)

        if s in BT_LEFT:
            htxt = f"<b>{s}</b><br>Deals: {v:,}"
        elif s == BT_CENTER:
            htxt = f"<b>Commit</b><br>Deals: {v:,}<br>ARR: €{m['commit_arr']:,.0f}"
        elif s == "Onboarding":
            htxt = f"<b>Onboarding</b><br>Deals: {m['onb_count']:,}<br>ARR: €{m['onb_arr']:,.0f}"
        elif s == "Adoption":
            htxt = (f"<b>Adoption</b><br>Deals: {m['adp_count']:,}"
                    f"<br>ARR: €{m['adp_arr']:,.0f}")
        elif s == "Renewal":
            htxt = (f"<b>Renewal</b><br>Deals: {m['ren_count']:,}"
                    f"<br>ARR: €{m['ren_arr']:,.0f}")
        else:
            htxt = (f"<b>Expansion (NRR)</b><br>ARR: €{m['exp_arr']:,.0f}"
                    f"<br>NRR: {m['nrr']:.1f}%<br>Expansion rev: €{m['total_exp']:,.0f}")

        if idx > 0:
            r_in = m["rates"].get((BT_STAGES[idx - 1], s))
            if r_in is not None:
                htxt += f"<br>Conv in: {r_in:.1f}%"
        if idx < len(BT_STAGES) - 1:
            r_out = m["rates"].get((s, BT_STAGES[idx + 1]))
            if r_out is not None:
                htxt += f"<br>Conv out: {r_out:.1f}%"

        fig.add_trace(go.Scatter(
            x=[x0, x1, x1, x0, x0], y=[h, h, -h, -h, h],
            fill="toself", fillcolor=_BT_COLORS[s],
            line=dict(color="white", width=0.7), mode="lines",
            showlegend=False,
            hovertemplate=htxt + "<extra></extra>",
            name=s,
        ))

        if s in BT_LEFT:
            lbl = f"<b>{s}</b><br>{v:,} deals"
        elif s == BT_CENTER:
            lbl = f"<b>Commit</b><br>{v:,} deals<br>€{m['commit_arr']/1e6:.1f}M ARR"
        elif s == "Onboarding":
            lbl = f"<b>Onboarding</b><br>€{m['onb_arr']/1e6:.1f}M ARR"
        elif s == "Adoption":
            lbl = f"<b>Adoption</b><br>€{m['adp_arr']/1e6:.1f}M ARR"
        elif s == "Renewal":
            lbl = f"<b>Renewal</b><br>€{m['ren_arr']/1e6:.1f}M ARR"
        else:
            lbl = f"<b>Expansion</b><br>€{m['exp_arr']/1e6:.1f}M ARR (NRR)"

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
        label = f"{rate:.1f}%"
        fig.add_annotation(
            x=xm, y=y_lbl, text=label, showarrow=False,
            font=dict(color=_BT_MUTED, size=9), align="center",
        )

    x_div = X[BT_CENTER] + _BT_BLK_W / 2
    fig.add_shape(
        type="line", x0=x_div, x1=x_div,
        y0=-(_BT_MAX_H + 0.06), y1=(_BT_MAX_H + 0.04),
        line=dict(color=HAIRLINE, dash="dot", width=1.2),
    )
    fig.add_annotation(
        x=X[BT_CENTER] - 0.1, y=_BT_MAX_H + 0.10,
        text="Pre-Sale", showarrow=False,
        font=dict(color="#ff4d8b", size=9), xanchor="right",
    )
    fig.add_annotation(
        x=X[BT_CENTER] + _BT_BLK_W + 0.1, y=_BT_MAX_H + 0.10,
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
