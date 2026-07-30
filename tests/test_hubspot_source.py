"""No live HubSpot portal to test against, so these mock requests.get and
check two things that matter most: the propertiesWithHistory -> transition-log
reconstruction (_deal_to_rows), and that every HubSpot failure mode raises
HubSpotConfigError rather than a raw requests/HTTP exception -- that's the
contract app.py's fallback-to-Demo-Data logic depends on."""
import pytest

from data.hubspot_source import (
    HubSpotConfigError,
    _deal_to_rows,
    _fetch_deals_with_history,
    _fetch_owners,
    fetch_hubspot_data,
)


class FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json


def _deal(deal_id, history, **props):
    base_props = {
        "dealname": f"Deal {deal_id}", "amount": "50000",
        "createdate": "2025-01-05T00:00:00Z", "hubspot_owner_id": "42",
        "bowtie_segment": "Mid-Market", "bowtie_motion": "Sales-led",
        "bowtie_churned": "false", "bowtie_expansion_revenue": "0",
        "bowtie_activated": "",
    }
    base_props.update(props)
    return {
        "id": deal_id,
        "properties": base_props,
        "propertiesWithHistory": {"bowtie_stage": history},
    }


def test_deal_to_rows_reconstructs_a_full_journey():
    history = [
        {"value": "Expansion", "timestamp": "2025-06-01T00:00:00Z"},
        {"value": "Renewal", "timestamp": "2025-05-01T00:00:00Z"},
        {"value": "Selection", "timestamp": "2025-01-05T00:00:00Z"},
        {"value": "Commit", "timestamp": "2025-01-15T00:00:00Z"},
    ]
    rows = _deal_to_rows(_deal("1", history), owners={"42": "Amara Okafor"})

    assert [r["stage_entered"] for r in rows] == ["Selection", "Commit", "Renewal", "Expansion"]
    assert [r["stage_exited"] for r in rows] == ["Commit", "Renewal", "Expansion", ""]
    assert rows[0]["days_in_stage"] == pytest.approx(10.0)
    assert rows[-1]["stage_exited"] == ""
    assert all(r["deal_id"] == "HS-1" for r in rows)
    assert all(r["rep_name"] == "Amara Okafor" for r in rows)
    assert all(r["churned"] is False for r in rows)  # bowtie_churned=false


def test_deal_to_rows_collapses_consecutive_duplicate_values():
    history = [
        {"value": "Selection", "timestamp": "2025-01-05T00:00:00Z"},
        {"value": "Selection", "timestamp": "2025-01-06T00:00:00Z"},  # no-op re-save
        {"value": "Commit", "timestamp": "2025-01-15T00:00:00Z"},
    ]
    rows = _deal_to_rows(_deal("2", history), owners={})
    assert [r["stage_entered"] for r in rows] == ["Selection", "Commit"]


def test_deal_to_rows_marks_churn_only_on_terminal_row():
    history = [
        {"value": "Selection", "timestamp": "2025-01-01T00:00:00Z"},
        {"value": "Commit", "timestamp": "2025-01-10T00:00:00Z"},
    ]
    rows = _deal_to_rows(_deal("3", history, bowtie_churned="true"), owners={})
    assert rows[0]["churned"] is False
    assert rows[-1]["churned"] is True


def test_deal_to_rows_puts_expansion_revenue_only_on_expansion_terminal_row():
    history = [
        {"value": "Renewal", "timestamp": "2025-01-01T00:00:00Z"},
        {"value": "Expansion", "timestamp": "2025-02-01T00:00:00Z"},
    ]
    rows = _deal_to_rows(_deal("4", history, bowtie_expansion_revenue="15000"), owners={})
    assert rows[0]["expansion_revenue"] == 0.0
    assert rows[-1]["expansion_revenue"] == 15000.0


def test_deal_to_rows_ignores_untagged_deals():
    assert _deal_to_rows(_deal("5", []), owners={}) == []


def test_deal_to_rows_sorts_out_of_order_history():
    # Deliberately reversed vs. chronological order -- the response isn't
    # documented as guaranteed-ordered, so the code must sort itself rather
    # than trust it.
    history = [
        {"value": "Commit", "timestamp": "2025-01-15T00:00:00Z"},
        {"value": "Selection", "timestamp": "2025-01-05T00:00:00Z"},
    ]
    rows = _deal_to_rows(_deal("6", history), owners={})
    assert [r["stage_entered"] for r in rows] == ["Selection", "Commit"]


def test_fetch_hubspot_data_raises_config_error_with_no_token():
    with pytest.raises(HubSpotConfigError, match="No HubSpot access token"):
        fetch_hubspot_data(None)


def test_fetch_hubspot_data_raises_on_401(monkeypatch):
    monkeypatch.setattr(
        "data.hubspot_source.requests.get",
        lambda *a, **k: FakeResponse(401, text="unauthorized"),
    )
    with pytest.raises(HubSpotConfigError, match="rejected the access token"):
        fetch_hubspot_data("bad-token")


def test_fetch_hubspot_data_raises_on_403(monkeypatch):
    monkeypatch.setattr(
        "data.hubspot_source.requests.get",
        lambda *a, **k: FakeResponse(403, text="forbidden"),
    )
    with pytest.raises(HubSpotConfigError, match="missing a required scope"):
        fetch_hubspot_data("token-missing-scopes")


def test_fetch_hubspot_data_raises_when_no_deals_are_tagged(monkeypatch):
    def fake_get(url, headers=None, params=None, timeout=None):
        if url.endswith("/owners"):
            return FakeResponse(200, {"results": []})
        return FakeResponse(200, {"results": [_deal("1", [])]})  # untagged

    monkeypatch.setattr("data.hubspot_source.requests.get", fake_get)
    with pytest.raises(HubSpotConfigError, match="no deals with a bowtie_stage"):
        fetch_hubspot_data("valid-token")


def test_fetch_deals_with_history_follows_pagination_cursor(monkeypatch):
    calls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append(params.get("after"))
        if params.get("after") is None:
            return FakeResponse(200, {
                "results": [_deal("1", [])],
                "paging": {"next": {"after": "cursor-2"}},
            })
        return FakeResponse(200, {"results": [_deal("2", [])]})

    monkeypatch.setattr("data.hubspot_source.requests.get", fake_get)
    deals = _fetch_deals_with_history("token")
    assert [d["id"] for d in deals] == ["1", "2"]
    assert calls == [None, "cursor-2"]


def test_fetch_deals_with_history_requests_at_most_50_per_page(monkeypatch):
    # HubSpot rejects limit > 50 on any request that includes
    # propertiesWithHistory (400 VALIDATION_ERROR) -- regression coverage for
    # that exact failure.
    seen_limits = []

    def fake_get(url, headers=None, params=None, timeout=None):
        seen_limits.append(params["limit"])
        return FakeResponse(200, {"results": [_deal("1", [])]})

    monkeypatch.setattr("data.hubspot_source.requests.get", fake_get)
    _fetch_deals_with_history("token")
    assert all(limit <= 50 for limit in seen_limits)


def test_fetch_owners_builds_id_to_name_map(monkeypatch):
    def fake_get(url, headers=None, params=None, timeout=None):
        return FakeResponse(200, {"results": [
            {"id": "42", "firstName": "Amara", "lastName": "Okafor"},
            {"id": "43", "firstName": "", "lastName": "", "email": "rep@example.com"},
        ]})

    monkeypatch.setattr("data.hubspot_source.requests.get", fake_get)
    owners = _fetch_owners("token")
    assert owners == {"42": "Amara Okafor", "43": "rep@example.com"}
