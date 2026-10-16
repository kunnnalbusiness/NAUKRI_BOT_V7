"""
BrowserManager: Unified Single-Chromium Process & Multi-Context Architecture.
Manages a single global Chromium process across all automation workers and sessions.
Provides thread-safe Playwright execution, per-(user, site) BrowserContext isolation,
warm context reuse across worker loops, automation asset route-blocking,
cgroup/psutil memory watchdog with hysteresis, and auto-recovery.
"""

import os
import time
import asyncio
import threading
from enum import Enum
from pathlib import Path
from typing import Dict, Tuple, Optional, Any, Set, List
import psutil

from backend.app.core.logging import logger
from common.paths import DATA_DIR, get_session_path

LOCK_PATH = DATA_DIR / "browser.lock"


class ThreadSafeProxy:
    """
    Transparent proxy wrapping Playwright objects (Page, ElementHandle, Locator, Mouse, etc.).
    Ensures ALL Playwright API invocations are safely dispatched to the dedicated
    event loop thread, completely eliminating thread-bound access violations.
    """

    def __init__(self, async_obj: Any, loop_runner: Any):
        self._async_obj = async_obj
        self._loop_runner = loop_runner

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._async_obj, name)
        if callable(attr):

            def _method_wrapper(*args, **kwargs):
                call_res = attr(*args, **kwargs)
                if asyncio.iscoroutine(call_res):
                    res = self._loop_runner(call_res)
                else:
                    res = call_res

                if res is not None and type(res).__module__.startswith("playwright."):
                    return ThreadSafeProxy(res, self._loop_runner)
                elif (
                    isinstance(res, list)
                    and res
                    and hasattr(res[0], "__module__")
                    and type(res[0]).__module__.startswith("playwright.")
                ):
                    return [ThreadSafeProxy(item, self._loop_runner) for item in res]
                return res

            return _method_wrapper
        else:
            if attr is not None and hasattr(attr, "__module__") and type(attr).__module__.startswith("playwright."):
                return ThreadSafeProxy(attr, self._loop_runner)
            return attr

    def __repr__(self) -> str:
        return f"<ThreadSafeProxy for {repr(self._async_obj)}>"


class WatchdogTier(str, Enum):
    NORMAL = "NORMAL"
    SOFT_LIMIT = "SOFT_LIMIT"  # >= 70%
    HARD_LIMIT = "HARD_LIMIT"  # >= 85%
    CRITICAL = "CRITICAL"  # >= 92%


class MemoryWatchdog:
    """
    Watches memory usage via Linux cgroups (v2 and v1) with fallback to psutil.
    Implements 4 operational tiers and strict hysteresis (resume only under 65%).
    """

    def __init__(self):
        self._last_sample_time = 0.0
        self._cached_percent = 0.0
        self._in_throttle_mode = False
        self._paused_engines: Set[Tuple[str, str]] = set()

    def get_memory_percent(self) -> float:
        """Returns effective memory usage percentage (0.0 to 100.0)."""
        now = time.time()
        if now - self._last_sample_time < 2.0 and self._cached_percent > 0:
            return self._cached_percent

        pct = self._read_cgroup_memory()
        if pct is None:
            pct = psutil.virtual_memory().percent

        self._cached_percent = float(pct)
        self._last_sample_time = now
        return self._cached_percent

    def _read_cgroup_memory(self) -> Optional[float]:
        """Reads cgroup v2 or v1 memory limits and usage."""
        try:
            # Cgroup v2
            cg2_cur = Path("/sys/fs/cgroup/memory.current")
            cg2_max = Path("/sys/fs/cgroup/memory.max")
            if cg2_cur.exists() and cg2_max.exists():
                cur_str = cg2_cur.read_text().strip()
                max_str = cg2_max.read_text().strip()
                if max_str != "max" and max_str.isdigit() and cur_str.isdigit():
                    max_bytes = int(max_str)
                    cur_bytes = int(cur_str)
                    if max_bytes > 0:
                        return (cur_bytes / max_bytes) * 100.0

            # Cgroup v1
            cg1_cur = Path("/sys/fs/cgroup/memory/memory.usage_in_bytes")
            cg1_max = Path("/sys/fs/cgroup/memory/memory.limit_in_bytes")
            if cg1_cur.exists() and cg1_max.exists():
                cur_bytes = int(cg1_cur.read_text().strip())
                max_bytes = int(cg1_max.read_text().strip())
                # cgroup v1 sets huge number (e.g. > 10^14) when unlimited
                if max_bytes < (1024**4) and max_bytes > 0:
                    return (cur_bytes / max_bytes) * 100.0
        except Exception:
            pass
        return None

    def evaluate(self) -> Tuple[WatchdogTier, str]:
        """
        Evaluates memory pressure and returns (Tier, Action).
        Tiers:
          - NORMAL (< 70%): Action 'NONE'
          - SOFT_LIMIT (>= 70%): Action 'RECYCLE_PAGES'
          - HARD_LIMIT (>= 85%): Action 'PAUSE_ENGINES'
          - CRITICAL (>= 92%): Action 'EMERGENCY_RELAUNCH'
        """
        pct = self.get_memory_percent()

        if pct >= 92.0:
            self._in_throttle_mode = True
            return WatchdogTier.CRITICAL, "EMERGENCY_RELAUNCH"
        elif pct >= 85.0:
            self._in_throttle_mode = True
            return WatchdogTier.HARD_LIMIT, "PAUSE_ENGINES"
        elif pct >= 70.0:
            return WatchdogTier.SOFT_LIMIT, "RECYCLE_PAGES"
        else:
            if pct < 65.0:
                self._in_throttle_mode = False
            return WatchdogTier.NORMAL, "NONE"

    def can_resume(self) -> bool:
        """Returns True only when memory pressure has subsided below 65% (hysteresis)."""
        pct = self.get_memory_percent()
        if self._in_throttle_mode:
            if pct < 65.0:
                self._in_throttle_mode = False
                return True
            return False
        return pct < 70.0

    def register_paused_engine(self, username: str, site: str):
        self._paused_engines.add((username.strip().lower(), site.lower()))

    def pop_resumable_engines(self) -> List[Tuple[str, str]]:
        if self.can_resume() and self._paused_engines:
            res = list(self._paused_engines)
            self._paused_engines.clear()
            return res
        return []


class BrowserManager:
    """
    Singleton manager enforcing ONE Chromium process for the entire backend.
    """

    _instance: Optional["BrowserManager"] = None
    _init_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "BrowserManager":
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._lock = threading.RLock()
        self._start_time = time.time()
        self._watchdog = MemoryWatchdog()
        self._playwright_instance = None
        self._browser = None
        self._browser_pid: Optional[int] = None
        self._contexts: Dict[Tuple[str, str], Any] = {}
        self._pages: Dict[Tuple[str, str], Any] = {}
        self._page_app_counts: Dict[Tuple[str, str], int] = {}
        self._active_status: Dict[Tuple[str, str], bool] = {}  # True if worker running

        # Thread-safe event loop for Playwright
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._start_event_loop()

        # Initialize process lock
        self.init_lock(str(LOCK_PATH))

    def _start_event_loop(self):
        """Starts dedicated background event loop thread for all Playwright calls."""
        ready_evt = threading.Event()

        def _runner():
            import sys
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                loop = asyncio.ProactorEventLoop()
            else:
                loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            ready_evt.set()
            loop.run_forever()

        self._loop_thread = threading.Thread(
            target=_runner, daemon=True, name="BrowserLoop"
        )
        self._loop_thread.start()
        ready_evt.wait(timeout=5.0)

    def run_coroutine(self, coro, timeout: float = 30.0):
        """Dispatches an async coroutine to the dedicated Playwright thread."""
        if not self._loop or not self._loop.is_running():
            raise RuntimeError("BrowserManager event loop is not running")
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=timeout)

    # ==========================================
    # Process Lock & Orphan Cleanup
    # ==========================================
    def init_lock(self, lock_path_str: str):
        """Acquires lockfile storing PID; handles dead PID reclamation."""
        path = Path(lock_path_str)
        path.parent.mkdir(parents=True, exist_ok=True)
        current_pid = os.getpid()

        with self._lock:
            if path.exists():
                try:
                    old_pid = int(path.read_text().strip())
                    if psutil.pid_exists(old_pid) and old_pid != current_pid:
                        logger.warning(
                            f"Another process (PID {old_pid}) holds the browser lock. Sticking to single-process rule."
                        )
                    else:
                        logger.info(f"Reclaiming stale lockfile from PID {old_pid}.")
                        path.write_text(str(current_pid), encoding="utf-8")
                except Exception:
                    path.write_text(str(current_pid), encoding="utf-8")
            else:
                path.write_text(str(current_pid), encoding="utf-8")

    def check_lock_status(self, lock_path_str: str, current_pid: int) -> bool:
        """Checks if the lock can be acquired by current_pid."""
        path = Path(lock_path_str)
        if not path.exists():
            return True
        try:
            pid_in_file = int(path.read_text().strip())
            if pid_in_file == current_pid:
                return True
            if psutil.pid_exists(pid_in_file):
                return False
            return True
        except Exception:
            return True

    def release_lock(self, lock_path_str: str):
        path = Path(lock_path_str)
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass

    def cleanup_orphan_chromium(self):
        """Cleans up a stale Chromium process owned by this application."""
        from common.browser_runtime import cleanup_orphaned_browser_process

        cleanup_orphaned_browser_process()

    # ==========================================
    # Lazy Single-Browser Lifecycle
    # ==========================================
    def is_running(self) -> bool:
        with self._lock:
            return self._browser is not None

    def _launch_browser_internal(self):
        """Internal launcher invoked on the dedicated thread."""

        async def _launch():
            from playwright.async_api import async_playwright
            from common.browser_runtime import connect_async

            if self._playwright_instance is None:
                self._playwright_instance = await async_playwright().start()

            return await connect_async(self._playwright_instance.chromium)

        return self.run_coroutine(_launch())

    def _ensure_browser(self):
        """Ensures the single Chromium process is running."""
        with self._lock:
            if self._browser is not None:
                try:
                    if self._browser.is_connected():
                        return
                except Exception as exc:
                    logger.warning("Could not verify Chromium CDP connection: %s", exc)

                logger.warning("Chromium CDP connection was lost; reconnecting.")
                self._browser = None
                self._browser_pid = None
                self._contexts.clear()
                self._pages.clear()
                self._page_app_counts.clear()
                self._active_status.clear()

            if self._browser is None:
                logger.info("Lazily launching unified Chromium process...")
                self.cleanup_orphan_chromium()
                self._browser = self._launch_browser_internal()
                try:
                    from common.browser_runtime import browser_process_metrics

                    self._browser_pid = browser_process_metrics()["pid"] or None
                except Exception:
                    pass

    # ==========================================
    # Context Management & Warm Reuse
    # ==========================================
    def get_or_create_context(
        self, username: str, site: str, is_automation: bool = True
    ) -> Any:
        """
        Gets existing warm context or creates a new one for (user, site).
        Context is kept warm across worker loops.
        """
        key = (username.strip().lower(), site.lower())

        with self._lock:
            self._ensure_browser()

            if key in self._contexts:
                ctx = self._contexts[key]
                try:
                    is_closed_fn = getattr(ctx, "is_closed", None)
                    if callable(is_closed_fn) and is_closed_fn() is True:
                        pass
                    else:
                        self._active_status[key] = True
                        return ctx
                except Exception:
                    pass

            # Create new context
            session_p = get_session_path(site, username=username)
            context_kwargs: Dict[str, Any] = {
                "viewport": {"width": 1280, "height": 800},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "locale": "en-IN",
                "timezone_id": "Asia/Kolkata",
                "extra_http_headers": {
                    "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
                },
            }
            if session_p.exists():
                context_kwargs["storage_state"] = str(session_p)

            async def _create():
                ctx_or_coro = self._browser.new_context(**context_kwargs)
                if asyncio.iscoroutine(ctx_or_coro):
                    ctx = await ctx_or_coro
                else:
                    ctx = ctx_or_coro

                # Stealth evasion
                if hasattr(ctx, "add_init_script"):
                    evasion_js = """
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    window.chrome = window.chrome || { runtime: {}, app: {} };
                    if (!navigator.languages || navigator.languages.length === 0) {
                        Object.defineProperty(navigator, 'languages', { get: () => ['en-IN', 'en-US', 'en'] });
                    }
                    """
                    ev_res = ctx.add_init_script(evasion_js)
                    if asyncio.iscoroutine(ev_res):
                        await ev_res

                # Route blocking for automation contexts
                if is_automation and hasattr(ctx, "route"):

                    async def route_filter(route):
                        req = route.request
                        res_type = req.resource_type
                        url = req.url.lower()
                        # Block heavy media, images, fonts, analytics
                        if res_type in ("image", "media", "font"):
                            await route.abort()
                            return
                        if any(
                            tracker in url
                            for tracker in (
                                "google-analytics.com",
                                "doubleclick.net",
                                "facebook.net",
                            )
                        ):
                            await route.abort()
                            return
                        await route.continue_()

                    r_res = ctx.route("**/*", route_filter)
                    if asyncio.iscoroutine(r_res):
                        await r_res

                return ctx

            ctx = self.run_coroutine(_create())
            self._contexts[key] = ctx
            self._active_status[key] = True
            self._page_app_counts[key] = 0
            logger.info(
                f"Initialized warm BrowserContext for user '{username}', site '{site}'."
            )
            return ctx

    def get_or_create_page(self, username: str, site: str) -> Any:
        """Gets active page for (user, site); recycles page if application count threshold met."""
        key = (username.strip().lower(), site.lower())
        ctx = self.get_or_create_context(username, site)

        # Check page recycling
        count = self._page_app_counts.get(key, 0)
        if count >= 35:  # Recycle threshold (25-50)
            logger.info(
                f"Recycling page for {key} after {count} applications to free DOM/JS memory."
            )
            self.recycle_page(username, site)

        with self._lock:
            if key in self._pages:
                pg = self._pages[key]
                try:
                    if not getattr(pg, "is_closed", lambda: False)():
                        return pg
                except Exception:
                    pass

            async def _new_p():
                pg_or_coro = ctx.new_page()
                if asyncio.iscoroutine(pg_or_coro):
                    return await pg_or_coro
                return pg_or_coro

            pg = self.run_coroutine(_new_p())
            self._pages[key] = pg
            return pg

    def increment_app_count(self, username: str, site: str):
        key = (username.strip().lower(), site.lower())
        self._page_app_counts[key] = self._page_app_counts.get(key, 0) + 1

    def recycle_page(self, username: str, site: str):
        """Closes and recreates the page within the same context."""
        key = (username.strip().lower(), site.lower())
        with self._lock:
            old_p = self._pages.pop(key, None)
            if old_p:

                async def _close(p):
                    try:
                        res = p.close()
                        if asyncio.iscoroutine(res):
                            await res
                    except Exception:
                        pass

                try:
                    self.run_coroutine(_close(old_p), timeout=5.0)
                except Exception:
                    pass
            self._page_app_counts[key] = 0

    def mark_engine_stopped(self, username: str, site: str):
        """Worker stopped: saves storage_state and sets page to about:blank. Context stays warm."""
        key = (username.strip().lower(), site.lower())
        with self._lock:
            self._active_status[key] = False
            ctx = self._contexts.get(key)
            if ctx:

                async def _save_and_idle():
                    if hasattr(ctx, "storage_state"):
                        try:
                            sp = get_session_path(site, username=username)
                            sp.parent.mkdir(parents=True, exist_ok=True)
                            res = ctx.storage_state(path=str(sp))
                            if asyncio.iscoroutine(res):
                                await res
                        except Exception:
                            pass
                    pg = self._pages.get(key)
                    if pg and hasattr(pg, "goto"):
                        try:
                            res = pg.goto("about:blank")
                            if asyncio.iscoroutine(res):
                                await res
                        except Exception:
                            pass

                try:
                    self.run_coroutine(_save_and_idle(), timeout=8.0)
                except Exception:
                    pass

    def close_context(self, username: str, site: str):
        """Explicitly closes context (on logout, user delete, or disconnect)."""
        key = (username.strip().lower(), site.lower())
        with self._lock:
            self._active_status.pop(key, None)
            self._page_app_counts.pop(key, None)
            pg = self._pages.pop(key, None)
            ctx = self._contexts.pop(key, None)

            async def _cleanup():
                if pg and hasattr(pg, "close"):
                    try:
                        res = pg.close()
                        if asyncio.iscoroutine(res):
                            await res
                    except Exception:
                        pass
                if ctx and hasattr(ctx, "close"):
                    try:
                        res = ctx.close()
                        if asyncio.iscoroutine(res):
                            await res
                    except Exception:
                        pass

            if pg or ctx:
                try:
                    self.run_coroutine(_cleanup(), timeout=5.0)
                except Exception:
                    pass

    def get_active_contexts(self) -> List[Tuple[str, str]]:
        with self._lock:
            return list(self._contexts.keys())

    # ==========================================
    # Metrics & Watchdog Telemetry
    # ==========================================
    def get_browser_tree_rss_mb(self) -> float:
        """Calculates total RSS in MB of Chromium and its child processes."""
        if not self._browser:
            return 0.0
        try:
            total_rss = 0
            if self._browser_pid and psutil.pid_exists(self._browser_pid):
                parent = psutil.Process(self._browser_pid)
                total_rss += parent.memory_info().rss
                for child in parent.children(recursive=True):
                    try:
                        total_rss += child.memory_info().rss
                    except Exception:
                        pass
            return round(total_rss / (1024 * 1024), 2)
        except Exception:
            return 0.0

    def get_metrics(self) -> Dict[str, Any]:
        """Provides snapshot metrics for /api/system/metrics."""
        tier, _ = self._watchdog.evaluate()
        mem_pct = self._watchdog.get_memory_percent()
        is_conn = False
        if self._browser:
            try:
                is_conn = getattr(self._browser, "is_connected", lambda: True)()
            except Exception:
                is_conn = True

        return {
            "memory_percent": round(mem_pct, 1),
            "browser_rss_mb": self.get_browser_tree_rss_mb(),
            "active_contexts": [f"{u}:{s}" for u, s in self.get_active_contexts()],
            "active_context_count": len(self._contexts),
            "watchdog_tier": tier.value,
            "browser_connected": is_conn,
            "uptime_seconds": int(time.time() - self._start_time),
        }

    def get_sync_page(self, username: str, site: str) -> ThreadSafeProxy:
        """
        Returns a thread-safe proxy to the warm active Page for (username, site).
        All Playwright method calls will be safely dispatched to the dedicated loop.
        """
        async_page = self.get_or_create_page(username, site)
        return ThreadSafeProxy(async_page, self.run_coroutine)

    def notify_application_completed(self, username: str, site: str) -> bool:
        """
        Increments application count. If threshold (35) is reached, recycles page.
        Returns True if page was recycled, False otherwise.
        """
        key = (username.strip().lower(), site.lower())
        with self._lock:
            self._page_app_counts[key] = self._page_app_counts.get(key, 0) + 1
            count = self._page_app_counts[key]
            if count >= 35:
                logger.info(
                    f"[BrowserManager] Auto-recycling page for {username}:{site} after {count} applications."
                )
                self.recycle_page(username, site)
                return True
        return False

    def verify_live_session(self, site: str, username: str) -> Dict[str, Any]:
        """
        Verifies live session on a throwaway page using the single Chromium process.
        Does NOT launch a new browser process.
        """
        from common.login_helper import CHECK_URLS, is_login_successful

        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        target_url = CHECK_URLS.get(site, "https://www.google.com")

        async def _verify():
            ctx = self.get_or_create_context(username, site, is_automation=False)
            page = await ctx.new_page()
            try:
                await page.goto(target_url, timeout=20000, wait_until="domcontentloaded")
                await asyncio.sleep(2.0)
                final_url = page.url or ""
                valid = is_login_successful(site, final_url)
                if (
                    "/login" in final_url.lower()
                    or "/authwall" in final_url.lower()
                    or "/checkpoint/" in final_url.lower()
                ):
                    valid = False
                return valid, final_url
            finally:
                try:
                    await page.close()
                except Exception:
                    pass

        try:
            is_valid, final_url = self.run_coroutine(_verify(), timeout=30.0)
            status_str = "Valid" if is_valid else "Expired"
            return {
                "present": True,
                "valid": is_valid,
                "status": status_str,
                "last_verified": now_str,
                "message": (
                    f"{site.title()} session verified live."
                    if is_valid
                    else f"{site.title()} session expired or login wall detected at {final_url}."
                ),
            }
        except Exception as e:
            return {
                "present": True,
                "valid": False,
                "status": "Check Failed",
                "last_verified": now_str,
                "message": f"Live verification error: {e}",
            }

    def deep_health_check(self) -> Dict[str, Any]:
        """
        Executes an on-demand deep health check by launching/verifying the single Chromium
        process and testing a throwaway about:blank page.
        """
        async def _check():
            self._ensure_browser()
            page = await self._browser.new_page()
            try:
                await page.goto("about:blank", timeout=10000)
                return True
            finally:
                try:
                    await page.close()
                except Exception:
                    pass

        try:
            self.run_coroutine(_check(), timeout=15.0)
            return {
                "status": "ok",
                "browser_launch": "ok",
                "browser_pid": self._browser_pid,
            }
        except Exception as e:
            return {
                "status": "error",
                "browser_launch": "failed",
                "error": str(e),
            }

    def check_memory_and_act(self):
        """
        Evaluates memory pressure and takes concrete action:
          - HARD_LIMIT / CRITICAL: pauses running engines with 'Paused - low memory'.
          - NORMAL (<65% hysteresis): resumes engines previously paused due to memory.
        """
        tier, _ = self._watchdog.evaluate()
        try:
            from common.engine_manager import engine_manager

            if tier in (WatchdogTier.HARD_LIMIT, WatchdogTier.CRITICAL):
                for (u, s) in list(self._active_status.keys()):
                    if self._active_status.get((u, s)):
                        self._watchdog.register_paused_engine(u, s)
                        engine_manager.pause_engine_for_memory(s, reason="Paused - low memory")
            elif tier == WatchdogTier.NORMAL and self._watchdog.can_resume():
                resumables = self._watchdog.pop_resumable_engines()
                for (u, s) in resumables:
                    engine_manager.resume_engine_from_memory(s)
        except Exception as e:
            logger.debug(f"check_memory_and_act notice: {e}")

    async def run_coroutine_async(self, coro: Any, timeout: float = 30.0) -> Any:
        """Dispatches an async coroutine to the dedicated Playwright loop and awaits it asynchronously from FastAPI's loop."""
        if not self._loop or not self._loop.is_running():
            raise RuntimeError("BrowserManager event loop is not running")
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return await asyncio.wait_for(asyncio.wrap_future(fut), timeout=timeout)

    def connect_over_cdp(self, endpoint_url: str) -> Any:
        """Connects over CDP to a running bot browser using Playwright on the dedicated loop."""
        async def _conn():
            from playwright.async_api import async_playwright

            if self._playwright_instance is None:
                self._playwright_instance = await async_playwright().start()
            return await self._playwright_instance.chromium.connect_over_cdp(endpoint_url)

        return self.run_coroutine(_conn())

    def create_interactive_login_session(self, username: str, site: str) -> Tuple[Any, Any, Any]:
        """
        Creates an interactive page and CDPSession on the dedicated loop.
        Returns (context, page, cdp_session).
        Does not close browser on exit.
        """
        ctx = self.get_or_create_context(username, site, is_automation=False)

        async def _init():
            page = await ctx.new_page()
            cdp = await ctx.new_cdpsession(page)
            return page, cdp

        page, cdp = self.run_coroutine(_init(), timeout=20.0)
        return ctx, page, cdp

    async def async_send_cdp(
        self, cdp: Any, method: str, params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Dispatches a CDP method call to the dedicated Playwright loop non-blockingly."""
        async def _do():
            return await cdp.send(method, params or {})
        fut = asyncio.run_coroutine_threadsafe(_do(), self._loop)
        return await asyncio.wrap_future(fut)

    async def async_close_interactive(self, page: Any = None, cdp: Any = None):
        """Cleanly detaches CDP and closes interactive page without closing the singleton browser."""
        async def _close():
            if cdp:
                try:
                    await cdp.detach()
                except Exception:
                    pass
            if page and hasattr(page, "close"):
                try:
                    await page.close()
                except Exception:
                    pass
        try:
            fut = asyncio.run_coroutine_threadsafe(_close(), self._loop)
            await asyncio.wait_for(asyncio.wrap_future(fut), timeout=5.0)
        except Exception:
            pass

    def reset_for_testing(self):
        """Resets in-memory state for unit tests."""
        with self._lock:
            self._browser = None
            self._contexts.clear()
            self._pages.clear()
            self._page_app_counts.clear()
            self._active_status.clear()


# Global Singleton Accessor
browser_manager = BrowserManager.get_instance()
