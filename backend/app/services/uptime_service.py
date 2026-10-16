"""
Uptime heartbeat service and public status page backend.

A daemon thread runs a heartbeat every 60 seconds and checks four components:
API (implicit), MongoDB (ping), Bot Worker (engine supervisor state) and
Browser Engine (Playwright executable availability). Results go to the
`uptime_checks` MongoDB collection with a 90-day TTL index; when MongoDB is
unavailable (local dev) a bounded in-memory store is used instead.

Incidents open automatically after 2 consecutive down checks and resolve on
recovery. The public summary endpoint never exposes user data, hostnames or
stack traces.
"""

import time
import logging
import threading
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


logger = logging.getLogger("uptime")

COMPONENTS = ("api", "mongodb", "bot_worker", "browser_engine")
COMPONENT_LABELS = {
    "api": "API",
    "mongodb": "MongoDB",
    "bot_worker": "Bot Worker",
    "browser_engine": "Browser Engine",
}

HEARTBEAT_INTERVAL = 60
TTL_DAYS = 90
INCIDENT_THRESHOLD = 2  # consecutive down checks before an incident opens

_checks_lock = (
    threading.RLock()
)  # reentrant: incident transitions call back into locked helpers
# Bounded in-memory fallback: last 24h of checks at 60 s resolution
_memory_checks: deque = deque(maxlen=24 * 60 * len(COMPONENTS))
_consecutive_down: Dict[str, int] = {}
_incidents: List[Dict[str, Any]] = []  # in-memory fallback only
_heartbeat_thread: Optional[threading.Thread] = None
_heartbeat_stop = threading.Event()
_started = False


# ---------------------------------------------------------------------------
# Storage layer (MongoDB with TTL index, in-memory fallback)
# ---------------------------------------------------------------------------


def _get_db():
    try:
        from backend.app.db.mongo import get_db

        return get_db()
    except Exception:
        return None


def _ensure_ttl_index(db) -> None:
    try:
        db.uptime_checks.create_index("checked_at", expireAfterSeconds=TTL_DAYS * 86400)
        db.uptime_incidents.create_index(
            "started_at", expireAfterSeconds=TTL_DAYS * 86400
        )
    except Exception as e:
        logger.warning(f"Uptime TTL index warning: {e}")


def _store_checks(records: List[Dict[str, Any]]) -> None:
    db = _get_db()
    if db is not None:
        try:
            db.uptime_checks.insert_many([dict(r) for r in records])
            return
        except Exception as e:
            logger.warning(f"Uptime check insert failed, using memory: {e}")
    with _checks_lock:
        _memory_checks.extend(records)


def _load_checks(since: datetime) -> List[Dict[str, Any]]:
    db = _get_db()
    if db is not None:
        try:
            out = []
            for doc in db.uptime_checks.find(
                {"checked_at": {"$gte": since.isoformat()}}
            ).sort("checked_at", 1):
                doc.pop("_id", None)
                out.append(doc)
            if out:
                return out
            # DB reachable but empty — still better than nothing
            return []
        except Exception as e:
            logger.warning(f"Uptime check read failed, using memory: {e}")
    with _checks_lock:
        return [
            r for r in _memory_checks if r.get("checked_at", "") >= since.isoformat()
        ]


# ---------------------------------------------------------------------------
# Component checks
# ---------------------------------------------------------------------------


def check_mongodb() -> Dict[str, Any]:
    start = time.perf_counter()
    try:
        from backend.app.db.mongo import get_db

        db = get_db()
        if db is None:
            return {"status": "up", "latency_ms": None, "detail": "local_store"}
        db.command("ping")
        return {
            "status": "up",
            "latency_ms": round((time.perf_counter() - start) * 1000, 1),
            "detail": "",
        }
    except Exception as e:
        return {"status": "down", "latency_ms": None, "detail": str(e)[:80]}


def check_bot_worker() -> Dict[str, Any]:
    """Operational when no supervisor is in Error state; idle counts as up."""
    try:
        from common.engine_manager import engine_manager

        states = engine_manager.get_status()
        for site, st in states.items():
            if st.get("status") == "Error":
                return {
                    "status": "down",
                    "latency_ms": None,
                    "detail": f"{site} engine error",
                }
        return {"status": "up", "latency_ms": None, "detail": ""}
    except Exception as e:
        return {"status": "down", "latency_ms": None, "detail": str(e)[:80]}


def check_browser_engine() -> Dict[str, Any]:
    """Verifies the Playwright browser binary is installed and verified via preflight."""
    try:
        from backend.app.core.preflight import run_browser_preflight

        start = time.perf_counter()
        pf = run_browser_preflight()
        if not pf.ok:
            return {
                "status": "down",
                "latency_ms": None,
                "detail": pf.message or "chromium binary missing",
            }
        return {
            "status": "up",
            "latency_ms": round((time.perf_counter() - start) * 1000, 1),
            "detail": "",
        }
    except Exception as e:
        return {"status": "down", "latency_ms": None, "detail": str(e)[:80]}


def run_checks() -> List[Dict[str, Any]]:
    """Runs one full heartbeat and records results + incident transitions."""
    ts = datetime.now().isoformat()
    results: List[Dict[str, Any]] = [
        {
            "component": "api",
            "status": "up",
            "latency_ms": 0.0,
            "detail": "",
            "checked_at": ts,
        }
    ]
    results.append({"component": "mongodb", **check_mongodb(), "checked_at": ts})
    results.append({"component": "bot_worker", **check_bot_worker(), "checked_at": ts})
    results.append(
        {"component": "browser_engine", **check_browser_engine(), "checked_at": ts}
    )

    for r in results:
        _record_incident_transition(r["component"], r["status"], ts)

    _store_checks(results)
    return results


def _record_incident_transition(component: str, status: str, ts: str) -> None:
    """Opens incidents after N consecutive downs; resolves on recovery."""
    with _checks_lock:
        if status == "down":
            _consecutive_down[component] = _consecutive_down.get(component, 0) + 1
            if _consecutive_down[component] == INCIDENT_THRESHOLD:
                _open_incident(component, ts)
        else:
            if _consecutive_down.get(component, 0) >= INCIDENT_THRESHOLD:
                _resolve_incident(component, ts)
            _consecutive_down[component] = 0


def _incident_store(db=None):
    return db.uptime_incidents if db is not None else None


def _open_incident(component: str, started_at: str) -> None:
    incident = {
        "component": component,
        "started_at": started_at,
        "resolved_at": None,
        "note": f"{COMPONENT_LABELS.get(component, component)} detected down by heartbeat",
        "manual": False,
    }
    db = _get_db()
    if db is not None:
        try:
            db.uptime_incidents.insert_one(dict(incident))
            return
        except Exception as e:
            logger.warning(f"Incident insert failed, using memory: {e}")
    with _checks_lock:
        _incidents.append(incident)
    logger.warning(f"[Uptime] Incident OPENED for {component} at {started_at}")


def _resolve_incident(component: str, resolved_at: str) -> None:
    db = _get_db()
    if db is not None:
        try:
            db.uptime_incidents.update_many(
                {"component": component, "resolved_at": None},
                {"$set": {"resolved_at": resolved_at}},
            )
            return
        except Exception as e:
            logger.warning(f"Incident resolve failed, using memory: {e}")
    with _checks_lock:
        for inc in reversed(_incidents):
            if inc["component"] == component and inc["resolved_at"] is None:
                inc["resolved_at"] = resolved_at
    logger.info(f"[Uptime] Incident RESOLVED for {component} at {resolved_at}")


def add_manual_note(component: str, note: str, author: str) -> Dict[str, Any]:
    """Admin-posted manual incident note."""
    incident = {
        "component": component if component in COMPONENTS else "api",
        "started_at": datetime.now().isoformat(),
        "resolved_at": datetime.now().isoformat(),
        "note": note[:500],
        "manual": True,
        "author": author,
    }
    db = _get_db()
    if db is not None:
        db.uptime_incidents.insert_one(dict(incident))
    else:
        with _checks_lock:
            _incidents.append(incident)
    return incident


def list_incidents(limit: int = 50) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    db = _get_db()
    if db is not None:
        try:
            for doc in db.uptime_incidents.find().sort("started_at", -1).limit(limit):
                doc.pop("_id", None)
                out.append(doc)
            return out
        except Exception as e:
            logger.warning(f"Incident list failed, using memory: {e}")
    with _checks_lock:
        out = sorted(_incidents, key=lambda i: i["started_at"], reverse=True)[:limit]
    return out


# ---------------------------------------------------------------------------
# Public summary (no sensitive data)
# ---------------------------------------------------------------------------


def _uptime_pct(checks: List[Dict[str, Any]]) -> Optional[float]:
    total = len(checks)
    if total == 0:
        return None
    up = sum(1 for c in checks if c.get("status") == "up")
    return round(up / total * 100, 2)


def get_status_summary() -> Dict[str, Any]:
    """Builds the public status page payload: banner, per-component uptime, incidents."""
    now = datetime.now()
    windows = {
        "24h": now - timedelta(hours=24),
        "7d": now - timedelta(days=7),
        "30d": now - timedelta(days=30),
        "90d": now - timedelta(days=90),
    }

    all_checks = _load_checks(windows["90d"])
    by_component: Dict[str, List[Dict[str, Any]]] = {c: [] for c in COMPONENTS}
    for c in all_checks:
        comp = c.get("component")
        if comp in by_component:
            by_component[comp].append(c)

    components_out = []
    down_count = 0
    for comp in COMPONENTS:
        checks = by_component[comp]
        latest = checks[-1] if checks else {"status": "up", "latency_ms": None}
        current = latest.get("status", "up")

        uptime = {}
        for label, since in windows.items():
            windowed = [
                c for c in checks if c.get("checked_at", "") >= since.isoformat()
            ]
            uptime[label] = _uptime_pct(windowed)

        # Daily bars for the 90-day strip (one block per day)
        daily: Dict[str, List[Dict[str, Any]]] = {}
        for c in checks:
            day = (c.get("checked_at") or "")[:10]
            if day:
                daily.setdefault(day, []).append(c)
        daily_bars = [
            {"date": day, "uptime_pct": _uptime_pct(rows)}
            for day, rows in sorted(daily.items())[-90:]
        ]

        if current != "up":
            down_count += 1

        components_out.append(
            {
                "key": comp,
                "label": COMPONENT_LABELS[comp],
                "status": current,
                "latency_ms": latest.get("latency_ms"),
                "uptime": uptime,
                "daily": daily_bars,
            }
        )

    if down_count == 0:
        overall = "operational"
        banner = "All systems operational"
    elif down_count < len(COMPONENTS):
        overall = "partial_outage"
        banner = "Partial outage"
    else:
        overall = "major_outage"
        banner = "Major outage"

    incidents = [
        {
            k: inc.get(k)
            for k in ("component", "started_at", "resolved_at", "note", "manual")
        }
        for inc in list_incidents(limit=20)
    ]

    return {
        "overall": overall,
        "banner": banner,
        "generated_at": now.isoformat(),
        "components": components_out,
        "incidents": incidents,
    }


# ---------------------------------------------------------------------------
# Background heartbeat thread
# ---------------------------------------------------------------------------


def _heartbeat_loop() -> None:
    # First check right away, then every HEARTBEAT_INTERVAL seconds
    while not _heartbeat_stop.is_set():
        try:
            run_checks()
        except Exception as e:
            logger.warning(f"Heartbeat check failed: {e}")
        _heartbeat_stop.wait(HEARTBEAT_INTERVAL)


def start_heartbeat() -> None:
    """Starts the 60 s heartbeat daemon (idempotent)."""
    global _heartbeat_thread, _started
    if _started and _heartbeat_thread and _heartbeat_thread.is_alive():
        return
    db = _get_db()
    if db is not None:
        _ensure_ttl_index(db)
    _heartbeat_stop.clear()
    _heartbeat_thread = threading.Thread(
        target=_heartbeat_loop, daemon=True, name="UptimeHeartbeat"
    )
    _heartbeat_thread.start()
    _started = True
    logger.info("Uptime heartbeat started (60 s interval).")


def stop_heartbeat() -> None:
    _heartbeat_stop.set()
