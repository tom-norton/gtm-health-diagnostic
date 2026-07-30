"""Live HubSpot connector: swaps the synthetic bowtie_data.csv for a real
portal's Deals. The diagnostic logic downstream (metrics/, advisor/,
charts/) does not change at all -- this module's only job is to hand back
two dataframes shaped exactly like data.loader.load_data()'s, built from
deals that carry the custom bowtie_* properties described in
docs/hubspot-setup.md.

Scoped to Selection -> Expansion (metrics.constants.DEAL_STAGES). HubSpot
deals don't naturally represent the pre-deal Awareness/Education stages, so
Live mode always returns an empty aggregate dataframe -- app.py shows a
banner explaining that those two blocks read zero in Live mode.

Reconstructing a transition log (one row per stage occupied, not just
"what stage is this deal in right now") is what lets every existing metric
-- conversion rates, days-in-stage, NRR/GRR, anomaly detection -- work
unmodified against real data. That reconstruction comes from HubSpot's
`propertiesWithHistory` parameter, which returns every value bowtie_stage
has held, each with a timestamp.
"""
from datetime import datetime

import pandas as pd
import requests

from metrics.constants import DEAL_STAGES, STAGE_ORDER

API_BASE = "https://api.hubapi.com"
DEAL_PROPERTIES = [
    "dealname", "amount", "createdate", "hubspot_owner_id",
    "bowtie_stage", "bowtie_segment", "bowtie_motion",
    "bowtie_churned", "bowtie_expansion_revenue", "bowtie_activated",
]
PAGE_SIZE = 100
MAX_PAGES = 50  # 5,000 deals -- a portfolio-project safety cap, not a production limit
REQUEST_TIMEOUT = 15

DEAL_COLUMNS = [
    "cohort_quarter", "stage_entered", "stage_exited", "deal_id",
    "company_name", "segment", "motion", "deal_value", "days_in_stage",
    "conversion_date", "rep_name", "churned", "expansion_revenue", "activated",
]
AGG_COLUMNS = [
    "cohort_quarter", "stage_entered", "stage_exited",
    "count_entered", "count_exited", "segment", "days_in_stage",
]


class HubSpotConfigError(Exception):
    """Raised for anything that means Live mode can't produce data -- no
    token, an invalid/expired token, missing scopes, or zero deals tagged
    with bowtie_stage. app.py catches this and falls back to Demo Data,
    showing this exception's message to the user rather than a stack
    trace -- see the README's "graceful degradation" note."""


def _headers(access_token):
    return {"Authorization": f"Bearer {access_token}"}


def _get(url, access_token, params):
    try:
        resp = requests.get(url, headers=_headers(access_token), params=params, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.RequestException as e:
        raise HubSpotConfigError(f"Couldn't reach HubSpot: {e}") from e

    if resp.status_code == 401:
        raise HubSpotConfigError(
            "HubSpot rejected the access token (401 Unauthorized). It may be "
            "wrong, expired, or rotated -- see docs/hubspot-setup.md."
        )
    if resp.status_code == 403:
        raise HubSpotConfigError(
            "HubSpot accepted the token but refused the request (403 "
            "Forbidden) -- the private app is most likely missing a required "
            "scope. It needs both crm.objects.deals.read and "
            "crm.objects.owners.read. See docs/hubspot-setup.md, 'Scopes.'"
        )
    if resp.status_code >= 400:
        raise HubSpotConfigError(f"HubSpot API error {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def _fetch_owners(access_token):
    """id -> display name, for turning hubspot_owner_id into rep_name."""
    owners = {}
    after = None
    for _ in range(MAX_PAGES):
        params = {"limit": PAGE_SIZE}
        if after:
            params["after"] = after
        data = _get(f"{API_BASE}/crm/v3/owners", access_token, params)
        for o in data.get("results", []):
            name = f"{o.get('firstName', '')} {o.get('lastName', '')}".strip()
            owners[str(o["id"])] = name or o.get("email") or "Unassigned"
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    return owners


def _fetch_deals_with_history(access_token):
    deals = []
    after = None
    for _ in range(MAX_PAGES):
        params = {
            "limit": PAGE_SIZE,
            "properties": ",".join(DEAL_PROPERTIES),
            "propertiesWithHistory": "bowtie_stage",
        }
        if after:
            params["after"] = after
        data = _get(f"{API_BASE}/crm/v3/objects/deals", access_token, params)
        deals.extend(data.get("results", []))
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    return deals


def _cohort_quarter(dt):
    return f"{dt.year}-Q{(dt.month - 1) // 3 + 1}"


def _parse_ts(raw):
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _bool_prop(value):
    return str(value).strip().lower() in ("true", "yes", "1")


def _deal_to_rows(deal, owners):
    """One deal's propertiesWithHistory.bowtie_stage entries -> one row per
    stage occupied, in the same shape as data/generate.py's deal rows."""
    props = deal.get("properties", {})
    history_raw = deal.get("propertiesWithHistory", {}).get("bowtie_stage", [])
    if not history_raw:
        return []  # never tagged -- not an error for the whole fetch, just skip it

    # HubSpot's history array isn't documented as guaranteed-ordered, so sort
    # explicitly by timestamp rather than trust the response order. Also
    # drops any value that isn't one of the six enumerated bowtie stages,
    # in case the property was ever set to something unexpected by hand.
    history = sorted(
        ({"stage": h["value"], "ts": _parse_ts(h["timestamp"])}
         for h in history_raw if h.get("value") in DEAL_STAGES),
        key=lambda h: h["ts"],
    )
    # Collapse consecutive no-op writes (the same value saved twice in a row).
    collapsed = []
    for h in history:
        if collapsed and collapsed[-1]["stage"] == h["stage"]:
            continue
        collapsed.append(h)
    if not collapsed:
        return []

    deal_id = f"HS-{deal['id']}"
    company = props.get("dealname") or f"Deal {deal['id']}"
    segment = props.get("bowtie_segment") or "Mid-Market"
    motion = props.get("bowtie_motion") or "Sales-led"
    deal_value = float(props.get("amount") or 0)
    rep_name = owners.get(str(props.get("hubspot_owner_id")), "Unassigned")
    churned = _bool_prop(props.get("bowtie_churned"))
    expansion_revenue = float(props.get("bowtie_expansion_revenue") or 0)
    activated_raw = props.get("bowtie_activated")
    activated = (_bool_prop(activated_raw)
                 if motion == "PLG" and activated_raw not in (None, "") else None)

    created = props.get("createdate")
    cohort = _cohort_quarter(_parse_ts(created)) if created else _cohort_quarter(collapsed[0]["ts"])

    rows = []
    for i, cur in enumerate(collapsed):
        is_last = i == len(collapsed) - 1
        nxt = None if is_last else collapsed[i + 1]
        days = (nxt["ts"] - cur["ts"]).total_seconds() / 86400 if nxt else 0.0
        rows.append({
            "cohort_quarter": cohort,
            "stage_entered": cur["stage"],
            "stage_exited": "" if is_last else nxt["stage"],
            "deal_id": deal_id,
            "company_name": company,
            "segment": segment,
            "motion": motion,
            "deal_value": deal_value,
            "days_in_stage": round(days, 1),
            "conversion_date": cur["ts"],
            "rep_name": rep_name,
            "churned": churned if is_last else False,
            "expansion_revenue": expansion_revenue if is_last and cur["stage"] == "Expansion" else 0.0,
            "activated": activated,
        })
    return rows


def fetch_hubspot_data(access_token):
    """Returns (agg_df, deal_df) built from a live HubSpot portal, in the
    same shape data.loader.load_data() returns. Raises HubSpotConfigError
    (never a raw requests/HTTP exception) for every failure mode, so callers
    can catch one exception type and fall back to Demo Data."""
    if not access_token:
        raise HubSpotConfigError(
            "No HubSpot access token configured -- see docs/hubspot-setup.md."
        )

    owners = _fetch_owners(access_token)
    deals = _fetch_deals_with_history(access_token)

    rows = []
    for deal in deals:
        rows.extend(_deal_to_rows(deal, owners))

    if not rows:
        raise HubSpotConfigError(
            "Connected to HubSpot, but found no deals with a bowtie_stage "
            "value set. Tag at least one deal with that property -- see "
            "docs/hubspot-setup.md, 'Tag a deal to test it.'"
        )

    deal_df = pd.DataFrame(rows, columns=DEAL_COLUMNS)
    deal_df["conversion_date"] = pd.to_datetime(deal_df["conversion_date"])
    deal_df["stage_entered"] = pd.Categorical(
        deal_df["stage_entered"], categories=STAGE_ORDER, ordered=True
    )
    agg_df = pd.DataFrame(columns=AGG_COLUMNS)
    return agg_df, deal_df
