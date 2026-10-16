"""
Preflight Verification for Automation Runtimes & Browser Drivers.
Ensures Playwright and Chromium are properly installed at build/startup time
without launching a heavy browser process during server boot.
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("preflight")


@dataclass
class PreflightResult:
    ok: bool
    error_code: Optional[str] = None
    message: str = ""
    admin_hint: str = ""
    executable_path: Optional[str] = None


def _import_playwright():
    """Isolated helper to test Playwright module import."""
    from playwright.sync_api import sync_playwright

    return sync_playwright


def _get_chromium_executable() -> Optional[str]:
    """
    Discovers the expected Chromium binary path using Playwright internals
    without launching a browser process.
    """
    try:
        from playwright._impl._driver import compute_driver_executable

        # Quick validation of driver
        compute_driver_executable()
    except Exception:
        pass

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            return p.chromium.executable_path
    except Exception as e:
        logger.debug(f"Unable to resolve chromium executable path: {e}")
        return None


# Global memoized result of startup preflight
_STARTUP_PREFLIGHT: Optional[PreflightResult] = None


def run_browser_preflight(force_refresh: bool = False) -> PreflightResult:
    """
    Executes a lightweight, non-invasive preflight check:
    1. Verifies playwright is importable.
    2. Resolves Chromium executable path.
    3. Confirms that executable actually exists on disk.
    Does NOT launch the browser.
    """
    global _STARTUP_PREFLIGHT
    if _STARTUP_PREFLIGHT is not None and not force_refresh:
        return _STARTUP_PREFLIGHT

    # 1. Test import
    try:
        _import_playwright()
    except Exception as e:
        res = PreflightResult(
            ok=False,
            error_code="BROWSER_NOT_INSTALLED",
            message=f"Playwright module could not be loaded: {e}",
            admin_hint="Run 'pip install -r requirements.txt' and verify Python dependencies.",
            executable_path=None,
        )
        _STARTUP_PREFLIGHT = res
        return res

    # 2. Test executable path
    try:
        exec_path = _get_chromium_executable()
    except Exception as e:
        res = PreflightResult(
            ok=False,
            error_code="BROWSER_NOT_INSTALLED",
            message=f"Failed resolving Chromium binary path: {e}",
            admin_hint="Verify PLAYWRIGHT_BROWSERS_PATH environment variable and run 'playwright install chromium'.",
            executable_path=None,
        )
        _STARTUP_PREFLIGHT = res
        return res

    if not exec_path or not os.path.exists(exec_path):
        res = PreflightResult(
            ok=False,
            error_code="BROWSER_NOT_INSTALLED",
            message=f"Playwright browser binary missing at resolved path '{exec_path}'",
            admin_hint="Run 'playwright install chromium' (or with system deps: 'playwright install --with-deps chromium'). Ensure PLAYWRIGHT_BROWSERS_PATH has read/exec permissions for the running user.",
            executable_path=exec_path,
        )
        _STARTUP_PREFLIGHT = res
        return res

    res = PreflightResult(
        ok=True,
        error_code=None,
        message="Playwright and Chromium binary verified successfully.",
        admin_hint="",
        executable_path=exec_path,
    )
    _STARTUP_PREFLIGHT = res
    return res
