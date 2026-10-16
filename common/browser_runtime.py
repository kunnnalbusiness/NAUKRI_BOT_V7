"""Owns one shared headless Chromium process and isolated Playwright contexts."""

import asyncio
import logging
import os
import subprocess
import threading
import time
import urllib.error
from urllib.parse import urlparse
import urllib.request
from pathlib import Path
from typing import Any

from common.paths import get_base_data_dir

logger = logging.getLogger("browser_runtime")
_lock = threading.RLock()
_process: subprocess.Popen | None = None
_started_at: float | None = None
_idle_since: float | None = None
_active_contexts: set[int] = set()
_last_recycle_reason: str | None = None
_port = int(os.environ.get("BROWSER_CDP_PORT", "9222"))
_user_data_dir = get_base_data_dir() / "cache" / "shared-chromium"
_pid_file = _user_data_dir.parent / "shared-chromium.pid"


def _endpoint() -> str:
    return f"http://127.0.0.1:{_port}"


def _browser_ready() -> bool:
    try:
        with urllib.request.urlopen(f"{_endpoint()}/json/version", timeout=0.5) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def _stop_stale_managed_process() -> None:
    if not _pid_file.exists():
        return
    try:
        pid = int(_pid_file.read_text(encoding="utf-8").strip())
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
        if f"--user-data-dir={_user_data_dir}" not in cmdline:
            logger.warning("Ignoring stale Chromium PID file whose process is not managed Chromium.")
            _pid_file.unlink(missing_ok=True)
            return
        os.kill(pid, 15)
        for _ in range(20):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            os.kill(pid, 9)
    except (OSError, ValueError):
        pass
    finally:
        _pid_file.unlink(missing_ok=True)


def _browser_launch_args(executable: str) -> list[str]:
    args = [
        executable,
        "--headless=new",
        "--disable-gpu",
        "--disable-extensions",
        f"--remote-debugging-port={_port}",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={_user_data_dir}",
        "about:blank",
    ]

    try:
        shm = os.statvfs("/dev/shm")
        shm_bytes = shm.f_frsize * shm.f_blocks
        logger.info("Chromium /dev/shm capacity: %.1f MiB.", shm_bytes / (1024 * 1024))
        if shm_bytes < 64 * 1024 * 1024:
            logger.warning("Small /dev/shm detected; using Chromium shared-memory fallback.")
            args.insert(4, "--disable-dev-shm-usage")
    except (AttributeError, OSError):
        logger.warning("Could not inspect /dev/shm; using Chromium shared-memory fallback.")
        args.insert(4, "--disable-dev-shm-usage")

    if hasattr(os, "geteuid") and os.geteuid() == 0:
        args.append("--no-sandbox")
        args.append("--disable-setuid-sandbox")
    return args


def cleanup_orphaned_browser_process() -> None:
    """Removes only a prior Chromium process identified by this app's PID marker."""
    with _lock:
        if _process is None or _process.poll() is not None:
            _stop_stale_managed_process()


def ensure_browser_process() -> str:
    """Launches Chromium once, or connects to the already managed local process."""
    global _process, _started_at, _idle_since
    with _lock:
        if _process and _process.poll() is None and _browser_ready():
            return _endpoint()
        _stop_stale_managed_process()
        if _browser_ready():
            raise RuntimeError(
                "The configured Chromium CDP port is occupied by an unmanaged process."
            )
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            executable = playwright.chromium.executable_path
        _user_data_dir.mkdir(parents=True, exist_ok=True)
        args = _browser_launch_args(executable)
        _process = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        _started_at = time.monotonic()
        _idle_since = _started_at
        _pid_file.write_text(str(_process.pid), encoding="utf-8")
        for _ in range(100):
            if _process.poll() is not None:
                raise RuntimeError(
                    f"Shared Chromium exited during startup (exit code {_process.returncode})."
                )
            if _browser_ready():
                logger.info("Shared headless Chromium is ready.")
                return _endpoint()
            time.sleep(0.1)
        asyncio.run(stop_browser_process())
        raise RuntimeError("Shared Chromium did not become ready within 10 seconds.")


def connect_sync(chromium: Any) -> Any:
    """Connects a synchronous Playwright client to the shared browser process."""
    return chromium.connect_over_cdp(ensure_browser_process())


async def connect_async(chromium: Any) -> Any:
    """Connects an asynchronous Playwright client to the shared browser process."""
    endpoint = await asyncio.to_thread(ensure_browser_process)
    return await chromium.connect_over_cdp(endpoint)


async def stop_browser_process() -> None:
    """Stops only the Chromium process launched by this application."""
    global _process, _started_at, _idle_since
    with _lock:
        process = _process
        _process = None
        _started_at = None
        _idle_since = None
        _active_contexts.clear()
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
            except OSError as exc:
                logger.warning("Could not stop managed Chromium process: %s", exc)
        else:
            _stop_stale_managed_process()
        _pid_file.unlink(missing_ok=True)


def active_browser_count() -> int:
    return int(_browser_ready())


def track_context(context: Any) -> Any:
    """Tracks a Playwright context until its close event for safe idle recycling."""
    global _idle_since
    context_id = id(context)
    with _lock:
        _active_contexts.add(context_id)
        _idle_since = None

    def context_closed(*_args: Any) -> None:
        global _idle_since
        with _lock:
            _active_contexts.discard(context_id)
            if not _active_contexts and _process and _process.poll() is None:
                _idle_since = time.monotonic()

    context.on("close", context_closed)
    return context


def maybe_recycle_browser() -> str | None:
    """Recycles Chromium only after the configured idle period or a 24-hour uptime."""
    global _last_recycle_reason
    with _lock:
        if not _process or _process.poll() is not None or _active_contexts:
            return None
        now = time.monotonic()
        idle_hours = float(os.environ.get("BROWSER_IDLE_RECYCLE_HOURS", "12"))
        idle_for = now - (_idle_since if _idle_since is not None else _started_at or now)
        uptime = now - (_started_at or now)
        if idle_for >= idle_hours * 3600:
            reason = f"idle for {idle_hours:g} hours"
        elif uptime >= 24 * 3600:
            reason = "uptime exceeded 24 hours"
        else:
            return None

    import asyncio

    asyncio.run(stop_browser_process())
    with _lock:
        _last_recycle_reason = reason
    logger.info("Recycled shared Chromium: %s.", reason)
    return reason


def browser_process_metrics() -> dict[str, Any]:
    """Returns the shared Chromium process-tree RSS and uptime without launching it."""
    with _lock:
        process = _process
        started_at = _started_at
        pid = process.pid if process and process.poll() is None else None
    rss_bytes = 0
    if pid is not None:
        try:
            import psutil
        except ImportError:
            logger.warning("psutil is unavailable; Chromium RSS is not measured.")
        else:
            try:
                root = psutil.Process(pid)
                processes = [root, *root.children(recursive=True)]
                rss_bytes = sum(
                    child.memory_info().rss
                    for child in processes
                    if child.is_running()
                )
            except psutil.Error:
                logger.warning("Could not inspect Chromium process-tree memory.")
    return {
        "rss_mb": round(rss_bytes / (1024 * 1024), 1),
        "uptime_seconds": (
            max(0, int(time.monotonic() - started_at)) if started_at else 0
        ),
        "pid": pid or 0,
        "active_contexts": len(_active_contexts),
        "last_recycle_reason": _last_recycle_reason or "",
    }


def install_resource_saver(context: Any, asynchronous: bool = False) -> None:
    """Avoids non-essential heavy resources while leaving login and job content intact."""
    def is_optional(route: Any) -> bool:
        request = route.request
        host = urlparse(request.url).hostname or ""
        return request.resource_type in {"image", "font", "media"} or any(
            host == domain or host.endswith(f".{domain}")
            for domain in (
                "google-analytics.com",
                "googletagmanager.com",
                "doubleclick.net",
            )
        )

    if asynchronous:
        async def async_route(route: Any) -> None:
            if is_optional(route):
                await route.abort()
            else:
                await route.continue_()

        context.route("**/*", async_route)
    else:
        def sync_route(route: Any) -> None:
            if is_optional(route):
                route.abort()
            else:
                route.continue_()

        context.route("**/*", sync_route)
