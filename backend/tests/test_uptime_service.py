"""
Uptime Service Unit Tests (in-memory fallback path) and Incident Lifecycle.
"""

from datetime import datetime

import pytest

from backend.app.services import uptime_service


@pytest.fixture(autouse=True)
def isolated_uptime_state(monkeypatch):
    """Force the in-memory store so tests never touch MongoDB."""
    monkeypatch.setattr(uptime_service, "_get_db", lambda: None)
    uptime_service._memory_checks.clear()
    uptime_service._incidents.clear()
    uptime_service._consecutive_down.clear()
    yield
    uptime_service._memory_checks.clear()
    uptime_service._incidents.clear()
    uptime_service._consecutive_down.clear()


class TestIncidentLifecycle:
    def test_no_incident_after_single_down(self):
        ts = datetime.now().isoformat()
        uptime_service._record_incident_transition("mongodb", "down", ts)
        assert len(uptime_service._incidents) == 0

    def test_incident_opens_after_two_consecutive_downs(self):
        ts = datetime.now().isoformat()
        uptime_service._record_incident_transition("mongodb", "down", ts)
        uptime_service._record_incident_transition("mongodb", "down", ts)
        assert len(uptime_service._incidents) == 1
        assert uptime_service._incidents[0]["component"] == "mongodb"
        assert uptime_service._incidents[0]["resolved_at"] is None

    def test_incident_resolves_on_recovery(self):
        ts = datetime.now().isoformat()
        uptime_service._record_incident_transition("bot_worker", "down", ts)
        uptime_service._record_incident_transition("bot_worker", "down", ts)
        recovery_ts = datetime.now().isoformat()
        uptime_service._record_incident_transition("bot_worker", "up", recovery_ts)
        assert uptime_service._incidents[0]["resolved_at"] == recovery_ts

    def test_two_downs_separated_by_up_do_not_open_incident(self):
        ts = datetime.now().isoformat()
        uptime_service._record_incident_transition("api", "down", ts)
        uptime_service._record_incident_transition("api", "up", ts)
        uptime_service._record_incident_transition("api", "down", ts)
        assert len(uptime_service._incidents) == 0

    def test_manual_note_recorded(self):
        inc = uptime_service.add_manual_note("api", "Maintenance window", "admin")
        assert inc["manual"] is True
        assert inc["note"] == "Maintenance window"
        assert len(uptime_service.list_incidents()) == 1


class TestStatusSummary:
    def test_summary_shape_and_no_sensitive_data(self):
        ts = datetime.now().isoformat()
        for comp in uptime_service.COMPONENTS:
            uptime_service._memory_checks.append(
                {
                    "component": comp,
                    "status": "up",
                    "latency_ms": 1.0,
                    "detail": "",
                    "checked_at": ts,
                }
            )
        summary = uptime_service.get_status_summary()
        assert summary["overall"] == "operational"
        assert summary["banner"] == "All systems operational"
        assert len(summary["components"]) == 4
        for comp in summary["components"]:
            assert comp["status"] == "up"
            assert set(comp["uptime"].keys()) == {"24h", "7d", "30d", "90d"}
        # Public payload must never contain raw internals
        assert "detail" not in str(summary["components"])
        assert "host" not in str(summary["components"]).lower()

    def test_summary_reports_down_component(self):
        ts = datetime.now().isoformat()
        for comp in uptime_service.COMPONENTS:
            status = "down" if comp == "mongodb" else "up"
            uptime_service._memory_checks.append(
                {
                    "component": comp,
                    "status": status,
                    "latency_ms": None,
                    "detail": "",
                    "checked_at": ts,
                }
            )
        summary = uptime_service.get_status_summary()
        assert summary["overall"] == "partial_outage"
        mongo = next(c for c in summary["components"] if c["key"] == "mongodb")
        assert mongo["status"] == "down"

    def test_uptime_percentage_calculation(self):
        ts = datetime.now().isoformat()
        # 3 up, 1 down => 75%
        for status in ("up", "up", "up", "down"):
            uptime_service._memory_checks.append(
                {
                    "component": "api",
                    "status": status,
                    "latency_ms": 0.0,
                    "detail": "",
                    "checked_at": ts,
                }
            )
        summary = uptime_service.get_status_summary()
        api = next(c for c in summary["components"] if c["key"] == "api")
        assert api["uptime"]["24h"] == 75.0
