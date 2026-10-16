"""
Engine Manager module.
Controls Naukri (Radar + Sweep) and LinkedIn worker engines as managed background threads.
Provides graceful start/stop, auto-restart with exponential backoff on crash,
daily quota handling (Waiting state), rapid toggle protection, and memory monitoring.
"""

import gc
import os
import time
import logging
import threading
from datetime import datetime
from typing import Dict, Any, Optional

try:
    import psutil
except ImportError:
    psutil = None

from common.runtime_config import get_config_value, set_config_value
from common.login_helper import has_session_file

logger = logging.getLogger("engine_manager")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )


class EngineManager:
    """Singleton manager for Naukri and LinkedIn automation engines."""

    def __init__(self):
        self._lock = threading.RLock()
        self._states: Dict[str, Dict[str, Any]] = {
            "naukri": {
                "status": "Stopped",
                "reason": "Initialized",
                "last_heartbeat": None,
                "enabled": False,
                "current_action": "Idle",
                "session_applied_count": 0,
                "daily_limit_exceeded": False,
                "limit_date": datetime.now().strftime("%Y-%m-%d"),
                "only_fresh_10min": False,
                "only_fresh": False,
                "fresh_threshold_minutes": 10,
                "pace_seconds": 3.0,
            },
            "linkedin": {
                "status": "Stopped",
                "reason": "Initialized",
                "last_heartbeat": None,
                "enabled": False,
                "current_action": "Idle",
                "session_applied_count": 0,
                "daily_limit_exceeded": False,
                "limit_date": datetime.now().strftime("%Y-%m-%d"),
                "only_fresh_10min": False,
                "only_fresh": False,
                "fresh_threshold_minutes": 10,
                "pace_seconds": 3.0,
            },
        }

        # Per-user isolated applied counts: {username: {"naukri": count, "linkedin": count}}
        self._user_applied_counts: Dict[str, Dict[str, int]] = {}
        # Per-user isolated daily limit state: {username: {site: {"daily_limit_exceeded": bool, "limit_date": str, "reason": str}}}
        self._user_daily_limits: Dict[str, Dict[str, Dict[str, Any]]] = {}
        # Active engine running user: {site: username}
        self._engine_active_user: Dict[str, Optional[str]] = {
            "naukri": None,
            "linkedin": None,
        }

        # Thread controllers
        self._stop_events: Dict[str, threading.Event] = {
            "naukri": threading.Event(),
            "linkedin": threading.Event(),
        }
        self._supervisor_threads: Dict[str, Optional[threading.Thread]] = {
            "naukri": None,
            "linkedin": None,
        }
        self._transition_locks: Dict[str, threading.Lock] = {
            "naukri": threading.Lock(),
            "linkedin": threading.Lock(),
        }

        # Memory monitor thread
        self._mem_stop = threading.Event()
        self._mem_thread = threading.Thread(
            target=self._memory_guard_loop, daemon=True, name="MemoryGuard"
        )
        self._mem_thread.start()

    def _memory_guard_loop(self):
        """Monitors RSS RAM usage and warns when memory is elevated."""
        threshold_mb = float(os.environ.get("MEMORY_GUARD_THRESHOLD_MB", "1500.0"))
        while not self._mem_stop.is_set():
            try:
                if psutil:
                    proc = psutil.Process(os.getpid())
                    rss_mb = proc.memory_info().rss / (1024 * 1024)
                    if rss_mb > threshold_mb:
                        logger.warning(
                            f"[Memory Guard Alert] Process RSS RAM is {rss_mb:.1f} MB (exceeds {threshold_mb:.0f} MB threshold). Triggering garbage collection."
                        )
                        gc.collect()
            except Exception:
                pass
            time.sleep(15)

    def get_status(self, username: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Returns the current status snapshot for all engines, strictly scoped by user/account."""
        with self._lock:
            today_str = datetime.now().strftime("%Y-%m-%d")
            u_clean = (username or "admin").strip().lower()
            res = {}
            for site in ("naukri", "linkedin"):
                # Auto-reset global if day has changed
                if self._states[site].get("limit_date") != today_str:
                    self._states[site]["daily_limit_exceeded"] = False
                    self._states[site]["limit_date"] = today_str

                state = dict(self._states[site])

                # Check user-isolated daily limit record
                user_limits = self._user_daily_limits.get(u_clean, {})
                user_site_limit = user_limits.get(site, {})
                if user_site_limit.get("limit_date") != today_str:
                    if (
                        u_clean in self._user_daily_limits
                        and site in self._user_daily_limits[u_clean]
                    ):
                        self._user_daily_limits[u_clean][site][
                            "daily_limit_exceeded"
                        ] = False
                    user_site_limit = {"daily_limit_exceeded": False}

                from backend.app.db.mongo import is_daily_limit_reached
                from common.paths import has_session_file
                from common.db import is_user_profile_complete

                is_user_limited = bool(
                    user_site_limit.get("daily_limit_exceeded", False)
                    or is_daily_limit_reached(u_clean, site, limit=50)
                )
                state["session_applied_count"] = self._user_applied_counts.get(
                    u_clean, {}
                ).get(site, 0)

                has_sess = has_session_file(
                    site, username=u_clean
                ) or user_site_limit.get("daily_limit_exceeded", False)
                prof_complete = True
                if u_clean not in ("admin", "user_a", "user_b"):
                    try:
                        prof_complete, _, _ = is_user_profile_complete(u_clean)
                    except Exception:
                        prof_complete = False

                active_user = self._engine_active_user.get(site)
                is_busy = bool(
                    active_user
                    and active_user != u_clean
                    and self._states[site].get("status") in ("Running", "Waiting")
                )
                is_running = bool(
                    active_user == u_clean
                    and self._states[site].get("status") in ("Running", "Waiting")
                )

                if is_user_limited:
                    state["daily_limit_exceeded"] = True
                    state["status"] = "Limit Reached"
                    state["reason"] = user_site_limit.get(
                        "reason",
                        f"Daily quota reached for {site.title()} — resets at midnight",
                    )
                    state["current_action"] = "Daily limit reached"
                    state["enabled"] = False
                elif is_running:
                    state["status"] = "Running"
                    state["enabled"] = True
                elif is_busy:
                    state["status"] = "Stopped"
                    state["reason"] = (
                        f"Engine is currently busy running for user '{active_user}'."
                    )
                    state["enabled"] = False
                else:
                    state["daily_limit_exceeded"] = False
                    state["status"] = "Stopped"
                    if not has_sess:
                        state["reason"] = (
                            f"Missing {site.title()} session. Use 'Add Session' to log in."
                        )
                    elif not prof_complete:
                        state["reason"] = (
                            "Profile incomplete. Update profile before starting."
                        )
                    else:
                        state["reason"] = "Ready to start"
                    state["current_action"] = "Idle"
                    state["enabled"] = False

                res[site] = state
            return res

    def reset_daily_limit(
        self, site: Optional[str] = None, username: Optional[str] = None
    ):
        """Resets daily limit status for specified site/user or all engines."""
        with self._lock:
            sites = [site] if site in ("naukri", "linkedin") else ["naukri", "linkedin"]
            today_str = datetime.now().strftime("%Y-%m-%d")

            if username:
                u_clean = username.strip().lower()
                if u_clean in self._user_daily_limits:
                    for s in sites:
                        if s in self._user_daily_limits[u_clean]:
                            self._user_daily_limits[u_clean][s] = {
                                "daily_limit_exceeded": False,
                                "limit_date": today_str,
                                "reason": "Limit cleared",
                            }
                if u_clean in self._user_applied_counts:
                    for s in sites:
                        self._user_applied_counts[u_clean][s] = 0
            else:
                self._user_daily_limits.clear()
                self._user_applied_counts.clear()

            for s in sites:
                self._states[s]["daily_limit_exceeded"] = False
                self._states[s]["limit_date"] = None
                self._states[s]["session_applied_count"] = 0
                if self._states[s]["status"] in ("Waiting", "Limit Reached"):
                    self._states[s]["status"] = "Stopped"
                self._states[s]["reason"] = "Daily limit cleared by reset"
                self._states[s]["current_action"] = "Idle"
            logger.info(
                f"Daily limit reset for sites={sites}, user={username or 'all'}"
            )

    def get_engine_state(
        self, site: str, username: Optional[str] = None
    ) -> Dict[str, Any]:
        """Returns state for a specific engine, scoped by user."""
        with self._lock:
            all_states = self.get_status(username=username)
            return dict(all_states.get(site, self._states.get(site, {})))

    def mark_daily_limit(
        self,
        site: str,
        reason: str = "Daily limit reached",
        username: Optional[str] = None,
    ):
        """Explicitly sets engine into Daily Limit Reached state, scoped to user/account."""
        with self._lock:
            today_str = datetime.now().strftime("%Y-%m-%d")
            u_clean = (
                (username or self._engine_active_user.get(site) or "admin")
                .strip()
                .lower()
            )

            if u_clean not in self._user_daily_limits:
                self._user_daily_limits[u_clean] = {}
            self._user_daily_limits[u_clean][site] = {
                "daily_limit_exceeded": True,
                "limit_date": today_str,
                "reason": reason,
            }

            self._states[site]["daily_limit_exceeded"] = True
            self._states[site]["limit_date"] = today_str
            self._states[site]["status"] = "Limit Reached"
            self._states[site]["reason"] = reason
            self._states[site]["current_action"] = reason
            self._states[site]["enabled"] = False
            self._states[site]["last_heartbeat"] = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            logger.warning(
                f"[{site.title()}] Marked DAILY LIMIT REACHED for user '{u_clean}': {reason}"
            )

    def _update_heartbeat(
        self, site: str, status: Optional[str] = None, reason: Optional[str] = None
    ):
        """Thread-safe update to engine heartbeat and status."""
        with self._lock:
            today_str = datetime.now().strftime("%Y-%m-%d")
            if self._states[site].get("limit_date") != today_str:
                self._states[site]["daily_limit_exceeded"] = False
                self._states[site]["limit_date"] = today_str

            self._states[site]["last_heartbeat"] = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            if reason is not None:
                if any(
                    q in reason.lower()
                    for q in [
                        "daily quota",
                        "limit reached",
                        "403009",
                        "easy apply limit",
                        "limit hit",
                        "limit exceeded",
                        "we limit easy apply",
                    ]
                ):
                    self._states[site]["daily_limit_exceeded"] = True
                    self._states[site]["status"] = "Limit Reached"
                    self._states[site]["reason"] = reason
                    self._states[site]["current_action"] = reason
                    self._states[site]["enabled"] = False
                elif not self._states[site].get("daily_limit_exceeded"):
                    self._states[site]["reason"] = reason

            if status is not None:
                # If daily limit reached today, prevent overwriting status with Running or Waiting
                if self._states[site].get("daily_limit_exceeded") and status in (
                    "Running",
                    "Waiting",
                ):
                    self._states[site]["status"] = "Limit Reached"
                elif (
                    self._states[site].get("status") == "Completed"
                    and status in ("Running", "Stopped")
                    and "goal reached"
                    in (self._states[site].get("reason") or "").lower()
                ):
                    # Preserve Completed state unless explicitly restarted
                    pass
                else:
                    self._states[site]["status"] = status

    def update_action(self, site: str, action: str):
        """Thread-safe update to engine current real-time activity string."""
        with self._lock:
            if site in self._states:
                # If daily limit reached, preserve limit reached notification in banner
                if self._states[site].get("daily_limit_exceeded"):
                    self._states[site]["current_action"] = "Daily limit reached"
                    self._states[site]["last_heartbeat"] = datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    return
                self._states[site]["current_action"] = action
                self._states[site]["last_heartbeat"] = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

    def increment_applied(self, site: str, username: Optional[str] = None):
        """Thread-safe increment to engine applied jobs count for this session, isolated per user."""
        with self._lock:
            u_clean = (
                (username or self._engine_active_user.get(site) or "admin")
                .strip()
                .lower()
            )

            cur_state_cnt = (
                self._states.get(site, {}).get("session_applied_count", 0) + 1
            )
            if site in self._states:
                self._states[site]["session_applied_count"] = cur_state_cnt

            if u_clean not in self._user_applied_counts:
                self._user_applied_counts[u_clean] = {}
            u_cnt = max(
                self._user_applied_counts[u_clean].get(site, 0) + 1, cur_state_cnt
            )
            self._user_applied_counts[u_clean][site] = u_cnt

            if u_cnt >= 50 or cur_state_cnt >= 50:
                self.mark_daily_limit(
                    site,
                    reason="Daily quota of 50 applications reached — resets at 12:00 AM",
                    username=u_clean,
                )

    def set_fresh_filter(
        self, site: str, enabled: bool, threshold_minutes: int = 10
    ) -> tuple[bool, Dict[str, Any]]:
        """Updates fresh job filtering flag and threshold minutes for engine dynamically."""
        if site not in ("naukri", "linkedin"):
            return False, {"error": f"Unknown engine '{site}'"}
        with self._lock:
            mins = max(1, int(threshold_minutes))
            self._states[site]["only_fresh"] = bool(enabled)
            self._states[site]["only_fresh_10min"] = bool(enabled)
            self._states[site]["fresh_threshold_minutes"] = mins
            logger.info(
                f"[{site.title()}] Fresh filter updated: enabled={enabled}, threshold_minutes={mins}"
            )
            return True, dict(self._states[site])

    def get_fresh_settings(self, site: str) -> tuple[bool, int]:
        """Returns (is_enabled, threshold_minutes) for specified site."""
        with self._lock:
            st = self._states.get(site, {})
            enabled = bool(st.get("only_fresh", st.get("only_fresh_10min", False)))
            mins = int(st.get("fresh_threshold_minutes", 10))
            return enabled, mins

    def set_pacing(self, site: str, pace_seconds: float) -> tuple[bool, Dict[str, Any]]:
        """Dynamically updates card inspection and action pacing delay (in seconds) for engine."""
        if site not in ("naukri", "linkedin"):
            return False, {"error": f"Unknown engine '{site}'"}
        with self._lock:
            pace = max(1.0, min(60.0, float(pace_seconds)))
            self._states[site]["pace_seconds"] = pace
            logger.info(f"[{site.title()}] Dynamic pacing updated to {pace:.1f}s")
            return True, dict(self._states[site])

    def get_pacing(self, site: str) -> float:
        """Returns current pacing delay (in seconds) for specified engine."""
        with self._lock:
            st = self._states.get(site, {})
            return float(st.get("pace_seconds", 3.0))

    def start_engine(
        self,
        site: str,
        username: Optional[str] = None,
        only_fresh_10min: bool = False,
        only_fresh: Optional[bool] = None,
        fresh_threshold_minutes: Optional[int] = None,
    ) -> tuple[bool, str]:
        """Starts worker thread for site. Thread-safe with rapid toggle protection."""
        if site not in ("naukri", "linkedin"):
            return False, f"Unknown engine '{site}'"

        u_clean = (username or "admin").strip().lower()

        with self._transition_locks[site]:
            with self._lock:
                # Check if already running
                current_thread = self._supervisor_threads[site]
                is_running = self._states[site]["status"] in (
                    "Running",
                    "Waiting",
                ) and self._states[site].get("enabled")
                if (current_thread and current_thread.is_alive()) or is_running:
                    current_owner = self._engine_active_user.get(site)
                    if current_owner == u_clean:
                        return True, f"{site.title()} engine is already running."
                    else:
                        return (
                            False,
                            f"Engine is currently busy running for user '{current_owner or 'another user'}'. Please wait for them to finish.",
                        )

                # Check session file and live validity (15-min TTL) for active user
                from common.login_helper import check_session_status

                session_status = check_session_status(
                    site, force_live_check=False, username=username
                )
                if not session_status.get("present") or not session_status.get("valid"):
                    self._states[site]["status"] = "Stopped"
                    err_msg = f"{site.title()} session invalid or expired. Reconnect required."
                    self._states[site]["reason"] = err_msg
                    self._states[site]["enabled"] = False
                    self._engine_active_user[site] = None
                    set_config_value(f"{site.upper()}_ENABLED", "false")
                    return (
                        False,
                        f"{site.title()} session invalid or expired. Please Reconnect.",
                    )

                # Check profile completeness for non-admin users
                if username and username.strip().lower() != "admin":
                    try:
                        from common.db import is_user_profile_complete

                        complete, p_reason, _ = is_user_profile_complete(username)
                        if not complete:
                            err_msg = f"Pehle profile complete karo: {p_reason}"
                            self._states[site]["status"] = "Stopped"
                            self._states[site]["reason"] = err_msg
                            self._states[site]["enabled"] = False
                            self._engine_active_user[site] = None
                            return False, err_msg
                    except Exception as pe:
                        logger.warning(f"Profile check error: {pe}")

                # Register active user and clear limit for this user
                self._engine_active_user[site] = u_clean
                self.reset_daily_limit(site, username=u_clean)

                # Resolve freshness parameters
                is_fresh_on = bool(
                    only_fresh if only_fresh is not None else only_fresh_10min
                )
                if fresh_threshold_minutes is None:
                    thresh_mins = int(
                        self._states[site].get("fresh_threshold_minutes", 10)
                    )
                else:
                    thresh_mins = max(1, int(fresh_threshold_minutes))

                # Store freshness flags in engine state
                self._states[site]["only_fresh"] = is_fresh_on
                self._states[site]["only_fresh_10min"] = is_fresh_on
                self._states[site]["fresh_threshold_minutes"] = thresh_mins

                # Reset stop event and start supervisor
                self._stop_events[site].clear()
                self._states[site]["status"] = "Running"
                fresh_label = (
                    f" · Fresh {thresh_mins}m filter ON" if is_fresh_on else ""
                )
                self._states[site]["reason"] = f"Starting workers...{fresh_label}"
                self._states[site]["enabled"] = True
                self._states[site]["last_heartbeat"] = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                set_config_value(f"{site.upper()}_ENABLED", "true")

                if site == "naukri":
                    target_fn = self._run_naukri_supervisor
                else:
                    target_fn = self._run_linkedin_supervisor

                kwargs = {
                    "username": username,
                    "only_fresh_10min": is_fresh_on,
                    "only_fresh": is_fresh_on,
                    "fresh_threshold_minutes": thresh_mins,
                }
                t = threading.Thread(
                    target=target_fn,
                    kwargs=kwargs,
                    daemon=True,
                    name=f"{site.title()}Supervisor",
                )
                self._supervisor_threads[site] = t
                t.start()

                fresh_msg = f" (Fresh {thresh_mins}m filter ON)" if is_fresh_on else ""
                logger.info(
                    f"[{site.title()}] Engine started for user '{username or 'admin'}'{fresh_msg}."
                )
                return True, f"{site.title()} engine started.{fresh_msg}"

    def stop_engine(
        self,
        site: str,
        timeout: float = 8.0,
        username: Optional[str] = None,
        is_admin: bool = False,
    ) -> tuple[bool, str]:
        """Gracefully stops worker thread for site."""
        if site not in ("naukri", "linkedin"):
            return False, f"Unknown engine '{site}'"

        u_clean = (username or "").strip().lower() if username else None

        with self._transition_locks[site]:
            with self._lock:
                current_owner = self._engine_active_user.get(site)
                if (
                    not is_admin
                    and u_clean
                    and current_owner
                    and current_owner != u_clean
                ):
                    return (
                        False,
                        f"Permission denied: Engine is running for user '{current_owner}'. Only the owner or an admin can stop it.",
                    )

                self._stop_events[site].set()
                self._states[site]["enabled"] = False
                set_config_value(f"{site.upper()}_ENABLED", "false")
                self._states[site]["reason"] = "Stopping..."
                self._engine_active_user[site] = None

            t = self._supervisor_threads[site]
            if t and t.is_alive():
                t.join(timeout=timeout)

            with self._lock:
                self._states[site]["status"] = "Stopped"
                self._states[site]["reason"] = "Stopped by user"
                self._states[site]["last_heartbeat"] = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                self._supervisor_threads[site] = None
                self._engine_active_user[site] = None

            logger.info(f"[{site.title()}] Engine stopped gracefully.")
            return True, f"{site.title()} engine stopped."

    def pause_engine_for_memory(self, site: str, reason: str = "Paused - low memory"):
        """Pauses a running engine under high memory pressure."""
        with self._lock:
            if site in self._states and self._states[site]["status"] in ("Running", "Waiting"):
                self._states[site]["previous_status"] = self._states[site]["status"]
                self._states[site]["status"] = "Paused"
                self._states[site]["reason"] = reason
                logger.warning(f"[{site.title()}] {reason}")

    def resume_engine_from_memory(self, site: str):
        """Resumes a paused engine when memory pressure drops below hysteresis threshold."""
        with self._lock:
            if site in self._states and self._states[site]["status"] == "Paused":
                self._states[site]["status"] = "Running"
                self._states[site]["reason"] = "Active - applying & scanning"
                logger.info(f"[{site.title()}] Resumed from memory pause.")

    def mark_session_removed(self, site: str, username: Optional[str] = None):
        """Immediately sets engine status to 'Session removed' and resets limit state so it NEVER shows 'Limit Reached'."""
        with self._lock:
            u_clean = (username or "admin").strip().lower()
            if (
                u_clean in self._user_daily_limits
                and site in self._user_daily_limits[u_clean]
            ):
                self._user_daily_limits[u_clean][site]["daily_limit_exceeded"] = False
            if site in self._states:
                self._states[site]["daily_limit_exceeded"] = False
                self._states[site]["status"] = "Session removed"
                self._states[site]["reason"] = f"{site.title()} session removed"
                self._states[site]["current_action"] = "Session removed"
                self._states[site]["enabled"] = False
                self._states[site]["last_heartbeat"] = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            self._engine_active_user[site] = None

    def _run_naukri_supervisor(
        self,
        username: Optional[str] = None,
        only_fresh_10min: bool = False,
        only_fresh: bool = False,
        fresh_threshold_minutes: int = 10,
    ):
        """Supervisor loop for Naukri bot (manages Radar and Sweep)."""
        stop_event = self._stop_events["naukri"]
        backoff = 5
        max_backoff = 60

        is_fresh_on = bool(only_fresh or only_fresh_10min)

        while not stop_event.is_set():
            try:
                # Import lazily so module is loaded in this thread context
                from common.profile import Profile
                from common import google_sheet
                from naukri_apply import radar_worker, sweep_worker

                if not has_session_file("naukri", username=username):
                    self._update_heartbeat(
                        "naukri", status="Error", reason="Session file missing"
                    )
                    break

                profile = Profile.load_for_user(username)
                already_applied = google_sheet.load_applied_jobs(username=username)
                applied_lock = threading.Lock()

                fresh_label = (
                    f" · Fresh {fresh_threshold_minutes}m" if is_fresh_on else ""
                )
                self._update_heartbeat(
                    "naukri",
                    status="Running",
                    reason=f"Radar & Sweep workers active{fresh_label}",
                )

                # Launch radar & sweep
                naukri_sub_stop = threading.Event()
                t_radar = threading.Thread(
                    target=radar_worker,
                    args=(profile, already_applied, applied_lock, naukri_sub_stop),
                    kwargs={
                        "only_fresh_10min": is_fresh_on,
                        "only_fresh": is_fresh_on,
                        "fresh_threshold_minutes": fresh_threshold_minutes,
                        "username": username,
                    },
                    daemon=True,
                    name="NaukriRadar",
                )
                t_sweep = threading.Thread(
                    target=sweep_worker,
                    args=(profile, already_applied, applied_lock, naukri_sub_stop),
                    kwargs={
                        "only_fresh_10min": is_fresh_on,
                        "only_fresh": is_fresh_on,
                        "fresh_threshold_minutes": fresh_threshold_minutes,
                        "username": username,
                    },
                    daemon=True,
                    name="NaukriSweep",
                )

                t_radar.start()
                t_sweep.start()

                # Monitor loop
                while not stop_event.is_set() and (
                    t_radar.is_alive() or t_sweep.is_alive()
                ):
                    if not self._states["naukri"].get("daily_limit_exceeded"):
                        self._update_heartbeat(
                            "naukri",
                            status="Running",
                            reason="Active - applying & scanning",
                        )
                    else:
                        self._update_heartbeat(
                            "naukri",
                            status="Limit Reached",
                            reason="Daily quota reached — resets at 12:00 AM",
                        )
                    time.sleep(3)

                if stop_event.is_set():
                    naukri_sub_stop.set()
                    t_radar.join(timeout=4)
                    t_sweep.join(timeout=4)
                    break

                # If workers stopped due to daily quota: recheck every 5 min
                if self._states["naukri"].get("daily_limit_exceeded"):
                    logger.info(
                        "[Naukri Supervisor] Quota hit. Will recheck every 5 min in case it resets."
                    )
                    recheck_interval = 300  # 5 minutes
                    elapsed = 0
                    while not stop_event.is_set() and self._states["naukri"].get(
                        "daily_limit_exceeded"
                    ):
                        remaining = recheck_interval - elapsed
                        self._update_heartbeat(
                            "naukri",
                            status="Limit Reached",
                            reason=f"Daily quota reached — rechecking in {max(0, remaining // 60)}m {max(0, remaining % 60)}s (resets 12:00 AM)",
                        )
                        time.sleep(1)
                        elapsed += 1
                        if elapsed >= recheck_interval:
                            # Auto-check if new day (auto-reset)
                            today_str = datetime.now().strftime("%Y-%m-%d")
                            if self._states["naukri"].get("limit_date") != today_str:
                                logger.info(
                                    "[Naukri Supervisor] New day detected — auto-clearing quota limit."
                                )
                                self.reset_daily_limit("naukri")
                            else:
                                logger.info(
                                    "[Naukri Supervisor] Recheck: quota still active for today."
                                )
                                self._update_heartbeat(
                                    "naukri",
                                    status="Limit Reached",
                                    reason="Daily quota reached — rechecking in 5 min",
                                )
                            elapsed = 0
                    if stop_event.is_set():
                        break
                    # Limit was cleared (auto-reset or manual) — restart workers
                    logger.info(
                        "[Naukri Supervisor] Limit cleared, restarting workers."
                    )
                    continue

                # Normal cycle completion — short delay then restart
                backoff = 5

            except Exception as e:
                err_str = str(e)
                if "daily quota" in err_str.lower() or "403009" in err_str:
                    logger.warning(
                        "[Naukri] Daily quota exceeded. Setting state to Limit Reached."
                    )
                    self.mark_daily_limit(
                        "naukri", reason="Daily quota reached — resets at 12:00 AM"
                    )
                    recheck_interval = 300
                    elapsed = 0
                    while not stop_event.is_set() and self._states["naukri"].get(
                        "daily_limit_exceeded"
                    ):
                        time.sleep(1)
                        elapsed += 1
                        self._update_heartbeat(
                            "naukri",
                            status="Limit Reached",
                            reason="Daily quota reached — resets at 12:00 AM",
                        )
                        if elapsed >= recheck_interval:
                            today_str = datetime.now().strftime("%Y-%m-%d")
                            if self._states["naukri"].get("limit_date") != today_str:
                                self.reset_daily_limit("naukri")
                            elapsed = 0
                else:
                    logger.error(f"[Naukri] Worker crashed: {err_str}")
                    self._update_heartbeat(
                        "naukri",
                        status="Error",
                        reason=f"Crash: {err_str[:80]} (Restarting in {backoff}s)",
                    )
                    for _ in range(backoff):
                        if stop_event.is_set():
                            break
                        time.sleep(1)
                    backoff = min(backoff * 2, max_backoff)

        if self._states["naukri"].get("status") not in ("Completed", "Limit Reached"):
            self._update_heartbeat("naukri", status="Stopped", reason="Stopped")

    def _run_linkedin_supervisor(
        self,
        username: Optional[str] = None,
        only_fresh_10min: bool = False,
        only_fresh: bool = False,
        fresh_threshold_minutes: int = 10,
    ):
        """Supervisor loop for LinkedIn bot."""
        stop_event = self._stop_events["linkedin"]
        backoff = 5
        max_backoff = 60

        is_fresh_on = bool(only_fresh or only_fresh_10min)

        def _linkedin_limit_wait():
            """Wait while limit active; recheck every 5 min for auto-reset on new day."""
            recheck_interval = 300  # 5 minutes
            elapsed = 0
            while not stop_event.is_set() and self._states["linkedin"].get(
                "daily_limit_exceeded"
            ):
                remaining = recheck_interval - elapsed
                self._update_heartbeat(
                    "linkedin",
                    status="Limit Reached",
                    reason=f"Easy Apply limit reached — rechecking in {max(0, remaining // 60)}m {max(0, remaining % 60)}s (resets midnight)",
                )
                time.sleep(1)
                elapsed += 1
                if elapsed >= recheck_interval:
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    if self._states["linkedin"].get("limit_date") != today_str:
                        logger.info(
                            "[LinkedIn Supervisor] New day detected — auto-clearing limit."
                        )
                        self.reset_daily_limit("linkedin")
                    else:
                        logger.info(
                            "[LinkedIn Supervisor] Recheck: limit still active for today."
                        )
                        self._update_heartbeat(
                            "linkedin",
                            status="Limit Reached",
                            reason="Easy Apply limit reached — rechecking in 5 min",
                        )
                    elapsed = 0

        while not stop_event.is_set():
            try:
                from linkedin_apply import run as run_linkedin

                if not has_session_file("linkedin", username=username):
                    self._update_heartbeat(
                        "linkedin", status="Error", reason="Session file missing"
                    )
                    break

                # If daily limit was hit previously today, stay in waiting mode with recheck
                if self._states["linkedin"].get("daily_limit_exceeded"):
                    _linkedin_limit_wait()
                    if stop_event.is_set():
                        break
                    continue

                fresh_label = (
                    f" (Fresh {fresh_threshold_minutes}m)" if is_fresh_on else ""
                )
                self._update_heartbeat(
                    "linkedin",
                    status="Running",
                    reason=f"LinkedIn Easy Apply active{fresh_label}",
                )

                # Run LinkedIn with stop_event, headless=True in background
                run_linkedin(
                    headless=True,
                    stop_event=stop_event,
                    continuous=False,
                    username=username,
                    only_fresh_10min=is_fresh_on,
                    only_fresh=is_fresh_on,
                    fresh_threshold_minutes=fresh_threshold_minutes,
                )

                if stop_event.is_set():
                    break

                # If goal was reached or status completed, halt cleanly
                if (
                    self._states["linkedin"].get("status") == "Completed"
                    or "goal reached"
                    in (self._states["linkedin"].get("reason") or "").lower()
                ):
                    logger.info(
                        "[LinkedIn Supervisor] Target goal completed today. Halting cleanly."
                    )
                    break

                # If daily limit was flagged during run, enter recheck wait
                if self._states["linkedin"].get("daily_limit_exceeded"):
                    logger.info(
                        "[LinkedIn Supervisor] Daily limit reached. Waiting with recheck every 5 min."
                    )
                    _linkedin_limit_wait()
                    if stop_event.is_set():
                        break
                    continue

                # Seamless continuous flow: immediately proceed to next search role with configured pace
                pace_wait = self.get_pacing("linkedin")
                time.sleep(min(pace_wait, 2.0))
                backoff = 2

            except Exception as e:
                err_str = str(e)
                if "easy apply limit" in err_str.lower() or "limit" in err_str.lower():
                    logger.warning(
                        "[LinkedIn] Easy Apply limit reached. Setting state to Limit Reached."
                    )
                    self.mark_daily_limit(
                        "linkedin",
                        reason="Daily Easy Apply limit reached — resets at midnight",
                    )
                    _linkedin_limit_wait()
                else:
                    logger.error(f"[LinkedIn] Worker crashed: {err_str}")
                    self._update_heartbeat(
                        "linkedin",
                        status="Error",
                        reason=f"Crash: {err_str[:80]} (Restarting in {backoff}s)",
                    )
                    for _ in range(backoff):
                        if stop_event.is_set():
                            break
                        time.sleep(1)
                    backoff = min(backoff * 2, max_backoff)

        if self._states["linkedin"].get("status") not in ("Completed", "Limit Reached"):
            self._update_heartbeat("linkedin", status="Stopped", reason="Stopped")

    def init_from_config(self):
        """Restores engine states from runtime config on application boot."""
        naukri_enabled = (
            get_config_value("NAUKRI_ENABLED", default="false").lower() == "true"
        )
        linkedin_enabled = (
            get_config_value("LINKEDIN_ENABLED", default="false").lower() == "true"
        )

        if naukri_enabled:
            logger.info("Restoring Naukri engine from saved config...")
            self.start_engine("naukri")

        if linkedin_enabled:
            logger.info("Restoring LinkedIn engine from saved config...")
            self.start_engine("linkedin")

    def shutdown_all(self):
        """Clean shutdown of all engines and monitoring."""
        self._mem_stop.set()
        self.stop_engine("naukri", timeout=5.0)
        self.stop_engine("linkedin", timeout=5.0)


# Global singleton instance
engine_manager = EngineManager()
