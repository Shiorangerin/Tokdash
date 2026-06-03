import os

import pytest


pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import tokdash.api as api


def _enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


@pytest.fixture(autouse=True)
def _reset_api_cache(monkeypatch):
    monkeypatch.setenv("TOKDASH_WARM_ON_START", "0")
    api._clear_cache()
    with api._cache_guard:
        api._key_locks.clear()
    yield
    api._clear_cache()
    with api._cache_guard:
        api._key_locks.clear()


@pytest.fixture
def synthetic_api_data(monkeypatch):
    """Keep default API smoke tests hermetic and cheap.

    The real local-log walk is useful as an integration/stress check, but it can
    reparse large session histories and compete with the installed dashboard
    service. Default tests should only verify routing/response shape.
    """

    def fake_usage(period, date_from, date_to):
        return {
            "period": period,
            "date_from": date_from,
            "date_to": date_to,
            "total_tokens": 123,
            "total_messages": 4,
            "comparison": {"previous_total_tokens": 100},
            "openclaw_models": [],
            "coding_apps": [],
        }

    def fake_tools(period):
        return {"apps": [], "all_models": [], "period": period}

    def fake_openclaw(period):
        return {"models": [], "contributions": [], "period": period}

    def fake_stats(year):
        return {"contributions": [], "stats": {"year": year}}

    def fake_sessions(tool, period, date_from=None, date_to=None):
        return {
            "tool": tool.strip().lower(),
            "period": period,
            "date_from": date_from,
            "date_to": date_to,
            "sessions": [{"session_id": "session-1"}],
            "latest_session": {"session_id": "session-1"},
        }

    def fake_session_detail(tool, session_id):
        return {"session": {"tool": tool, "session_id": session_id}, "turns": []}

    def fake_codex_sessions(period):
        return {
            "tool": "codex",
            "period": period,
            "sessions": [{"session_id": "codex-session-1"}],
            "latest_session": {"session_id": "codex-session-1"},
        }

    def fake_codex_session_detail(session_id):
        return {"session": {"tool": "codex", "session_id": session_id}, "turns": []}

    monkeypatch.setattr(api, "compute_usage_with_comparison", fake_usage)
    monkeypatch.setattr(api, "get_tools_data", fake_tools)
    monkeypatch.setattr(api, "get_openclaw_data", fake_openclaw)
    monkeypatch.setattr(api, "compute_stats", fake_stats)
    monkeypatch.setattr(api, "get_sessions_data", fake_sessions)
    monkeypatch.setattr(api, "get_session_detail", fake_session_detail)
    monkeypatch.setattr(api, "get_codex_sessions_data", fake_codex_sessions)
    monkeypatch.setattr(api, "get_codex_session_detail", fake_codex_session_detail)


def test_api_endpoints_and_dashboard_smoke(synthetic_api_data):
    client = TestClient(api.app)

    usage = client.get("/api/usage", params={"period": "today"}).json()
    assert "total_tokens" in usage
    assert "total_messages" in usage
    assert "comparison" in usage
    assert "openclaw_models" in usage
    assert "coding_apps" in usage

    tools = client.get("/api/tools", params={"period": "today"}).json()
    assert "apps" in tools
    assert "all_models" in tools

    for tool in ("codex", "claude", "opencode"):
        sessions = client.get("/api/sessions", params={"tool": tool, "period": "today"}).json()
        assert "sessions" in sessions
        assert "latest_session" in sessions
        assert sessions.get("tool") == tool

        latest = sessions.get("latest_session")
        if latest and latest.get("session_id"):
            detail = client.get("/api/session", params={"tool": tool, "session_id": latest["session_id"]}).json()
            assert "session" in detail
            assert "turns" in detail

    codex_sessions = client.get("/api/codex/sessions", params={"period": "today"}).json()
    assert "sessions" in codex_sessions
    assert "latest_session" in codex_sessions

    latest_codex = codex_sessions.get("latest_session")
    if latest_codex and latest_codex.get("session_id"):
        codex_detail = client.get("/api/codex/session", params={"session_id": latest_codex["session_id"]}).json()
        assert "session" in codex_detail
        assert "turns" in codex_detail

    openclaw = client.get("/api/openclaw", params={"period": "today"}).json()
    assert "models" in openclaw
    assert "contributions" in openclaw

    stats = client.get("/api/stats").json()
    assert "contributions" in stats
    assert "stats" in stats

    stats_year = client.get("/api/stats", params={"year": 2025}).json()
    assert "contributions" in stats_year
    assert "stats" in stats_year

    manifest = client.get("/manifest.webmanifest").text
    assert "Tokdash" in manifest

    sw_response = client.get("/sw.js")
    assert "no-store" in sw_response.headers["cache-control"]
    sw = sw_response.text
    assert "service worker" in sw.lower()
    assert "__TOKDASH_CACHE_NAME__" not in sw
    assert 'const CACHE_NAME = "tokdash-' in sw

    html_response = client.get("/")
    assert "no-store" in html_response.headers["cache-control"]
    html = html_response.text
    assert "Tokdash" in html
    assert "Sessions" in html

    icon_response = client.get("/static/icons/icon-192.png")
    assert icon_response.status_code == 200
    assert "no-store" in icon_response.headers["cache-control"]


def test_api_custom_date_ranges_and_validation(synthetic_api_data):
    client = TestClient(api.app)

    usage = client.get("/api/usage", params={"date_from": "2026-04-08", "date_to": "2026-04-08"})
    assert usage.status_code == 200
    assert "comparison" in usage.json()

    sessions = client.get(
        "/api/sessions",
        params={"tool": "codex", "date_from": "2026-04-08", "date_to": "2026-04-08"},
    )
    assert sessions.status_code == 200
    assert sessions.json()["tool"] == "codex"

    missing_bound = client.get("/api/usage", params={"date_from": "2026-04-08"})
    assert missing_bound.status_code == 400
    assert "required" in missing_bound.json()["detail"]

    malformed = client.get("/api/usage", params={"date_from": "2026/04/08", "date_to": "2026-04-08"})
    assert malformed.status_code == 400
    assert "Invalid date format" in malformed.json()["detail"]

    reversed_range = client.get("/api/usage", params={"date_from": "2026-04-09", "date_to": "2026-04-08"})
    assert reversed_range.status_code == 400
    assert "on or before" in reversed_range.json()["detail"]


@pytest.mark.skipif(
    not _enabled("TOKDASH_RUN_REAL_API_SMOKE"),
    reason="set TOKDASH_RUN_REAL_API_SMOKE=1 to walk real local logs; this is intentionally heavy",
)
def test_api_endpoints_against_real_local_logs():
    """Opt-in integration/stress check for the real parser stack."""
    client = TestClient(api.app)

    usage = client.get("/api/usage", params={"period": "today"}).json()
    assert "total_tokens" in usage
    assert "total_messages" in usage
    assert "comparison" in usage

    stats = client.get("/api/stats").json()
    assert "contributions" in stats
    assert "stats" in stats
