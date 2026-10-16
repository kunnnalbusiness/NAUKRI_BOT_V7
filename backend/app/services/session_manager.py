"""
Interactive browser streaming via Chrome DevTools Protocol (CDP) screencast over WebSocket.
Enables headless remote login directly in the web dashboard without X11 or VNC daemons,
with strict state machine (idle -> launching -> ready -> saved), clean orphan process termination,
and double-typing-proof input dispatching.
"""

import asyncio
import json
import logging
import os
import time
from typing import Optional, Dict, Any
from urllib.parse import urlparse
from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    CDPSession,
)
from starlette.websockets import WebSocket, WebSocketDisconnect

from common.login_helper import SITES, CHECK_URLS, is_login_successful
from common.browser_runtime import connect_async
from common.paths import get_session_path
from common.access_detector import async_check_page_access_denied
from backend.app.db.mongo import (
    save_encrypted_session,
    get_decrypted_session,
    update_user_settings,
)
from backend.app.services.browser_manager import browser_manager

logger = logging.getLogger("session_manager")


def _find_site_page(
    browser: Browser, site: str
) -> tuple[Optional[BrowserContext], Optional[Page]]:
    domain = "linkedin.com" if site == "linkedin" else "naukri.com"
    for context in browser.contexts:
        for page in context.pages:
            hostname = (urlparse(page.url).hostname or "").lower()
            if hostname == domain or hostname.endswith(f".{domain}"):
                return context, page
    return None, None


class ActiveLoginSession:
    """Represents an active interactive login or live check session over CDP."""

    def __init__(self, site: str, mode: str = "login"):
        self.site = site
        self.mode = mode
        if mode == "live_check":
            self.url = CHECK_URLS.get(
                site, SITES.get(site, "https://www.naukri.com/nlogin/login")
            )
        else:
            self.url = SITES.get(site, "https://www.naukri.com/nlogin/login")
        self.start_time = time.time()
        self.timeout_seconds = 300  # 5 minutes
        self.cancelled = False
        self.saved = False
        self.ready = False
        self.first_frame_sent = False
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.cdp: Optional[CDPSession] = None
        self.pw = None
        self.is_attached = False
        self.stream_fps: int = 15
        self.min_frame_interval: float = 1.0 / 15.0

    def set_fps(self, fps: int):
        """Dynamically updates the target frame rate and throttled interval."""
        self.stream_fps = max(1, min(60, int(fps)))
        self.min_frame_interval = 1.0 / float(self.stream_fps)


class SessionStreamManager:
    """
    Manages active CDP streaming login and live check sessions.
    Keeps independent user/site sessions isolated while cleaning up CDP connections.
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self._active: Dict[tuple[str, str], ActiveLoginSession] = {}
        self._launch_in_progress: Dict[tuple[str, str], ActiveLoginSession] = {}
        self._pw: Optional[Any] = None

    def is_active(self) -> bool:
        return bool(self._active or self._launch_in_progress)

    def get_active_site(self) -> Optional[str]:
        return next((session.site for session in self._active.values()), None)

    async def cancel_active(self) -> bool:
        """Cancels any currently running login session."""
        async with self._lock:
            sessions = list(self._active.values())
            if not sessions:
                return False
            for session in sessions:
                session.cancelled = True
                await self._cleanup(session)
            return True

    async def _cleanup(self, session: Optional[ActiveLoginSession] = None):
        """Cleans up active browser instance and CDP session without leaving orphan processes."""
        if session is None:
            for active_session in list(self._active.values()):
                await self._cleanup(active_session)
            return

        sess = session
        for key, active_session in list(self._active.items()):
            if active_session is sess:
                self._active.pop(key, None)
        for key, launching_session in list(self._launch_in_progress.items()):
            if launching_session is sess:
                self._launch_in_progress.pop(key, None)

        try:
            if sess.cdp:
                await asyncio.wait_for(sess.cdp.detach(), timeout=2.0)
        except Exception:
            pass

        if getattr(sess, "is_attached", False):
            try:
                if sess.browser:
                    await asyncio.wait_for(sess.browser.close(), timeout=2.0)
            except Exception:
                pass

            logger.info(
                f"[{sess.site}] Live Check detached from running bot browser."
            )
            return

        try:
            if sess.page and not sess.page.is_closed():
                await asyncio.wait_for(sess.page.close(), timeout=2.0)
        except Exception:
            pass
        try:
            if sess.context:
                await asyncio.wait_for(sess.context.close(), timeout=2.0)
        except Exception:
            pass
        try:
            if sess.browser:
                await asyncio.wait_for(sess.browser.close(), timeout=2.0)
        except Exception:
            pass

        logger.info(
            f"[{sess.site}] Chromium browser and context cleanly terminated."
        )

    async def start_streaming(
        self,
        site: str,
        ws: WebSocket,
        mode: str = "login",
        username: str = "admin",
        target_fps: Optional[int] = None,
    ):
        """Runs the interactive CDP screencast loop over WebSocket for login or live check."""
        reuse_existing = False
        session_key = (username.strip().lower(), site.lower())
        async with self._lock:
            active_session = self._active.get(session_key)
            if (
                active_session is not None
                and active_session.mode == mode
                and not active_session.cancelled
                and active_session.page is not None
                and not active_session.page.is_closed()
                and active_session.cdp is not None
            ):
                logger.info(
                    f"[{site}] Reusing active running browser session without restart or page refresh."
                )
                reuse_existing = True
                session = active_session
            else:
                if active_session is not None:
                    logger.info(
                        f"Replacing previous active session for {active_session.site} with fresh connection."
                    )
                    active_session.cancelled = True
                    try:
                        await self._cleanup(active_session)
                    except Exception as ce:
                        logger.debug(f"Previous session cleanup notice: {ce}")

                launching_session = self._launch_in_progress.get(session_key)
                if launching_session is not None:
                    await ws.send_json(
                        {
                            "type": "error",
                            "message": f"{site.title()} browser session is already starting. Please wait a few seconds.",
                        }
                    )
                    return

                session = ActiveLoginSession(site, mode=mode)
                self._active[session_key] = session
                self._launch_in_progress[session_key] = session

        # Determine target streaming FPS from param or user settings
        try:
            from backend.app.db.mongo import get_user_settings

            user_cfg = get_user_settings(username)
            effective_fps = max(
                1,
                min(
                    60,
                    int(
                        target_fps
                        if target_fps is not None
                        else user_cfg.get("stream_fps", 15)
                    ),
                ),
            )
        except Exception:
            effective_fps = 15

        session.set_fps(effective_fps)
        monitor_task = None
        last_frame_time = 0.0

        try:
            mode_label = "Live Check" if session.mode == "live_check" else "Login"

            if reuse_existing:
                # Browser already launched and on page - DO NOT launch or reload page!
                cdp = session.cdp
                page = session.page
                context = session.context
                browser = session.browser
                is_attached_to_bot = getattr(session, "is_attached", False)

                # Send ready status immediately so frontend remains strictly READY
                await ws.send_json(
                    {
                        "type": "status",
                        "status": "ready",
                        "fps": session.stream_fps,
                        "message": (
                            "Browser ready. Log in below."
                            if session.mode == "login"
                            else "Live inspection active."
                        ),
                    }
                )

                # Screencast frame handler with dynamic FPS throttle
                async def on_screencast_frame(event):
                    nonlocal last_frame_time
                    try:
                        if session.cancelled or session.saved:
                            return
                        now = time.time()
                        session_id = event.get("sessionId")
                        data = event.get("data")
                        metadata = event.get("metadata", {})

                        if cdp:
                            await cdp.send(
                                "Page.screencastFrameAck", {"sessionId": session_id}
                            )

                        if now - last_frame_time < session.min_frame_interval:
                            return
                        last_frame_time = now

                        await ws.send_json(
                            {"type": "frame", "data": data, "metadata": metadata}
                        )
                    except Exception:
                        pass

                cdp.on("Page.screencastFrame", on_screencast_frame)

            else:
                # State Machine: LAUNCHING
                await ws.send_json(
                    {
                        "type": "status",
                        "status": "launching",
                        "message": f"Starting realistic Chromium session for {site.title()} ({mode_label})...",
                    }
                )

                if self._pw is None:
                    self._pw = await async_playwright().start()
                pw = self._pw
                session.pw = pw

                is_attached_to_bot = False
                browser = None
                context = None
                page = None

                # If Live Check, try attaching to running bot browser CDP
                bot_port = None
                if session.mode == "live_check":
                    from common.engine_manager import engine_manager

                    eng_state = engine_manager.get_engine_state(
                        site, username=username
                    )
                    is_engine_active = eng_state.get("status") in (
                        "Running",
                        "Waiting",
                        "Queued",
                    )

                    bot_port = int(os.environ.get("BROWSER_CDP_PORT", "9222"))

                    if bot_port:

                        def _probe_cdp(port: int) -> bool:
                            import urllib.request

                            try:
                                req = urllib.request.Request(
                                    f"http://127.0.0.1:{port}/json/version",
                                    headers={"User-Agent": "Dashboard"},
                                )
                                with urllib.request.urlopen(req, timeout=0.8) as resp:
                                    return resp.status == 200
                            except Exception:
                                return False

                        max_attempts = 3 if is_engine_active else 1
                        for attempt in range(max_attempts):
                            try:
                                is_open = await asyncio.to_thread(_probe_cdp, bot_port)
                                if is_open:
                                    browser = await pw.chromium.connect_over_cdp(
                                        f"http://127.0.0.1:{bot_port}"
                                    )
                                    if browser.contexts:
                                        context, page = _find_site_page(browser, site)
                                        if page:
                                            session.browser = browser
                                            session.context = context
                                            session.page = page
                                            session.is_attached = True
                                            is_attached_to_bot = True
                                            logger.info(
                                                f"[{site}] Live Check attached to running bot browser on port {bot_port}!"
                                            )
                                            break
                            except Exception as e:
                                logger.debug(
                                    f"[{site}] Bot probe attempt {attempt+1}: {e}"
                                )

                            if is_engine_active and not is_attached_to_bot:
                                await ws.send_json(
                                    {
                                        "type": "status",
                                        "status": "launching",
                                        "message": f"Connecting to live bot stream ({attempt+1}/{max_attempts})...",
                                    }
                                )
                                await asyncio.sleep(1.0)
                            else:
                                break

                        if is_engine_active and not is_attached_to_bot:
                            await ws.send_json(
                                {
                                    "type": "error",
                                    "message": f"{site.title()} bot is currently busy or initializing. Try again in a few seconds.",
                                }
                            )
                            session.cancelled = True
                            return

                # Launch standalone Chromium with realistic desktop parameters and anti-bot evasions
                if not is_attached_to_bot:
                    browser = await connect_async(pw.chromium)
                    session.browser = browser

                    session_p = get_session_path(site, username=username)

                    # Restore session from MongoDB if not on disk
                    if not session_p.exists():
                        restored_json = get_decrypted_session(username, site)
                        if restored_json:
                            session_p.parent.mkdir(parents=True, exist_ok=True)
                            session_p.write_text(restored_json, encoding="utf-8")
                            logger.info(
                                f"Restored {site} session from MongoDB for {username}"
                            )

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

                    context = await browser.new_context(**context_kwargs)
                    session.context = context

                    # Inject stealth evasions to mask Playwright automation signature
                    await context.add_init_script(
                        """
                        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                        window.chrome = window.chrome || { runtime: {}, app: {} };
                        if (!navigator.languages || navigator.languages.length === 0) {
                            Object.defineProperty(navigator, 'languages', { get: () => ['en-IN', 'en-US', 'en'] });
                        }
                    """
                    )

                    page = await context.new_page()
                    session.page = page

                cdp = await context.new_cdp_session(page)
                session.cdp = cdp

                # Screencast frame handler with 15 FPS throttle and First-Frame Ready Trigger
                async def on_screencast_frame(event):
                    nonlocal last_frame_time
                    try:
                        if session.cancelled or session.saved:
                            return
                        now = time.time()
                        session_id = event.get("sessionId")
                        data = event.get("data")
                        metadata = event.get("metadata", {})

                        if cdp:
                            await cdp.send(
                                "Page.screencastFrameAck", {"sessionId": session_id}
                            )

                        # STATE MACHINE: Emit READY strictly when first frame arrives!
                        if not session.first_frame_sent:
                            session.first_frame_sent = True
                            session.ready = True
                            await ws.send_json(
                                {
                                    "type": "status",
                                    "status": "ready",
                                    "fps": session.stream_fps,
                                    "message": (
                                        "Browser ready. Log in below."
                                        if session.mode == "login"
                                        else "Live inspection active."
                                    ),
                                }
                            )

                        # Throttle frame delivery using user's configured stream interval
                        if now - last_frame_time < session.min_frame_interval:
                            return
                        last_frame_time = now

                        await ws.send_json(
                            {"type": "frame", "data": data, "metadata": metadata}
                        )
                    except Exception:
                        pass

                cdp.on("Page.screencastFrame", on_screencast_frame)

                # Start Screencast with optimized parameters (quality: 60, reasonable dimensions)
                await cdp.send(
                    "Page.startScreencast",
                    {
                        "format": "jpeg",
                        "quality": 60,
                        "maxWidth": 1024,
                        "maxHeight": 640,
                        "everyNthFrame": 1,
                    },
                )
                if self._launch_in_progress.get(session_key) is session:
                    self._launch_in_progress.pop(session_key, None)

                # Navigate to target page if standalone session
                if not is_attached_to_bot:
                    try:
                        resp = await page.goto(
                            session.url, wait_until="domcontentloaded", timeout=25000
                        )
                        resp_status = resp.status if resp else None
                        # Verify page is not blocked by Access Denied / 403 / Checkpoint
                        is_denied, denied_msg = await async_check_page_access_denied(
                            page, site=site, response_status=resp_status
                        )
                        if is_denied:
                            try:
                                await ws.send_json(
                                    {
                                        "type": "status",
                                        "status": "access_denied",
                                        "message": denied_msg,
                                    }
                                )
                            except Exception:
                                pass
                    except Exception as e:
                        logger.debug(f"Navigation timeout/notice: {e}")

            # Monitor task for auto-saving on login completion
            if session.mode != "live_check":

                async def monitor_login():
                    while not session.cancelled and not session.saved:
                        if time.time() - session.start_time > session.timeout_seconds:
                            try:
                                await ws.send_json(
                                    {
                                        "type": "status",
                                        "status": "timeout",
                                        "message": "Login session timed out (5 minutes limit reached).",
                                    }
                                )
                            except Exception:
                                pass
                            session.cancelled = True
                            break

                        try:
                            curr_url = page.url or ""
                            logged_in = is_login_successful(site, curr_url)

                            # Check for Cloud Datacenter Challenge / Checkpoint
                            is_denied, denied_msg = (
                                await async_check_page_access_denied(page, site=site)
                            )
                            if is_denied:
                                try:
                                    await ws.send_json(
                                        {
                                            "type": "status",
                                            "status": "warning",
                                            "message": denied_msg,
                                        }
                                    )
                                except Exception:
                                    pass

                            if not logged_in and context:
                                try:
                                    cookies = await context.cookies()
                                    cookie_names = {c.get("name") for c in cookies}
                                    if site == "linkedin":
                                        li_at_val = next(
                                            (
                                                c.get("value")
                                                for c in cookies
                                                if c.get("name") == "li_at"
                                            ),
                                            "",
                                        )
                                        if len(li_at_val) > 10:
                                            logged_in = True
                                    elif site == "naukri":
                                        if any(
                                            k in cookie_names
                                            for k in (
                                                "nauk_acc",
                                                "nk_auth",
                                                "USER_INFO",
                                            )
                                        ):
                                            logged_in = True
                                    elif not any(
                                        m in curr_url.lower()
                                        for m in [
                                            "/login",
                                            "nlogin",
                                            "/uas/login",
                                            "/authwall",
                                        ]
                                    ):
                                        if site == "naukri":
                                            el = await page.query_selector(
                                                ".nI-gNb-drawer, .view-profile-wrapper, a[href*='mnjuser']"
                                            )
                                            if el:
                                                logged_in = True
                                        elif site == "linkedin":
                                            el = await page.query_selector(
                                                "nav#global-nav, .global-nav, .feed-identity-module, a[href*='/in/']"
                                            )
                                            if el:
                                                logged_in = True
                                except Exception:
                                    pass

                            if logged_in:
                                await ws.send_json(
                                    {
                                        "type": "status",
                                        "status": "saving",
                                        "message": "Login detected! Encrypting and saving session state...",
                                    }
                                )
                                await asyncio.sleep(1.5)

                                saved_path = get_session_path(site, username=username)
                                saved_path.parent.mkdir(parents=True, exist_ok=True)
                                save_ok = False

                                for attempt in range(3):
                                    try:
                                        await context.storage_state(
                                            path=str(saved_path)
                                        )
                                        save_ok = True
                                        break
                                    except Exception:
                                        await asyncio.sleep(1.0)

                                if save_ok:
                                    session.saved = True
                                    try:
                                        session_content = saved_path.read_text(
                                            encoding="utf-8"
                                        )
                                        save_encrypted_session(
                                            username, site, session_content
                                        )
                                        update_user_settings(
                                            username,
                                            session_metadata={
                                                site: {
                                                    "logged_in": True,
                                                    "last_verified": time.strftime(
                                                        "%Y-%m-%d %H:%M:%S"
                                                    ),
                                                }
                                            },
                                        )
                                        logger.info(
                                            f"Backed up {site} session for user {username} to MongoDB."
                                        )
                                    except Exception as me:
                                        logger.warning(
                                            f"Failed to backup session to Mongo: {me}"
                                        )

                                    # Update in-memory session cache immediately
                                    try:
                                        from common.login_helper import (
                                            _SESSION_CACHE,
                                            _get_cache_key,
                                        )

                                        cache_key = _get_cache_key(
                                            site, username=username
                                        )
                                        _SESSION_CACHE[cache_key] = {
                                            "present": True,
                                            "valid": True,
                                            "status": "Valid",
                                            "last_verified": time.strftime(
                                                "%Y-%m-%d %H:%M:%S"
                                            ),
                                            "message": "Session newly saved",
                                            "_mtime": (
                                                saved_path.stat().st_mtime
                                                if saved_path.exists()
                                                else time.time()
                                            ),
                                        }
                                    except Exception:
                                        pass

                                    # Clear any previous daily limit lock for this newly authenticated account
                                    try:
                                        from common.engine_manager import engine_manager

                                        engine_manager.reset_daily_limit(
                                            site, username=username
                                        )
                                    except Exception:
                                        pass

                                    await ws.send_json(
                                        {
                                            "type": "status",
                                            "status": "saved",
                                            "message": f"✓ {site.upper()} session verified and backed up! You may close this window.",
                                        }
                                    )
                                    break
                        except Exception as e:
                            logger.debug(f"Login monitor check: {e}")

                        await asyncio.sleep(2.0)

                monitor_task = asyncio.create_task(monitor_login())

            # WebSocket message loop for user interactions (STRICT SINGLE PATH KEYBOARD DISPATCH)
            while not session.cancelled:
                try:
                    data_str = await ws.receive_text()
                    msg = json.loads(data_str)
                    msg_type = msg.get("type")

                    if msg_type == "cancel":
                        session.cancelled = True
                        break

                    if msg_type == "mouse":
                        event_name = msg.get("event")
                        x = msg.get("x", 0)
                        y = msg.get("y", 0)
                        btn = msg.get("button", "none")
                        click_count = msg.get("clickCount", 1)

                        if event_name in (
                            "mousePressed",
                            "mouseReleased",
                            "mouseMoved",
                        ):
                            cdp_btn = (
                                btn if btn in ("left", "middle", "right") else "none"
                            )
                            cdp_type = event_name
                            await cdp.send(
                                "Input.dispatchMouseEvent",
                                {
                                    "type": cdp_type,
                                    "x": x,
                                    "y": y,
                                    "button": cdp_btn,
                                    "clickCount": click_count,
                                },
                            )
                        elif event_name == "wheel":
                            dx = msg.get("deltaX", 0)
                            dy = msg.get("deltaY", 0)
                            await cdp.send(
                                "Input.dispatchMouseEvent",
                                {
                                    "type": "mouseWheel",
                                    "x": x,
                                    "y": y,
                                    "deltaX": dx,
                                    "deltaY": dy,
                                },
                            )

                    # STRICT SINGLE-PATH KEYBOARD INPUT
                    elif msg_type == "type_text":
                        # Text insertion (all printable chars & paste use this path ONLY)
                        text_to_type = msg.get("text", "")
                        if text_to_type:
                            await cdp.send("Input.insertText", {"text": text_to_type})

                    elif msg_type == "key":
                        # Non-printable control keys (Backspace, Enter, Tab, Arrow keys, etc.)
                        ev_type = msg.get("event")  # "keyDown" or "keyUp"
                        key_val = msg.get("key", "")
                        code_val = msg.get("code", "")
                        if ev_type in ("keyDown", "keyUp") and key_val:
                            await cdp.send(
                                "Input.dispatchKeyEvent",
                                {
                                    "type": ev_type,
                                    "key": key_val,
                                    "code": code_val,
                                    "windowsVirtualKeyCode": msg.get("keyCode", 0),
                                },
                            )

                    elif msg_type in ("set_fps", "change_fps"):
                        new_fps = max(1, min(60, int(msg.get("fps", 15))))
                        session.set_fps(new_fps)
                        try:
                            from backend.app.db.mongo import update_user_settings

                            update_user_settings(username, stream_fps=new_fps)
                        except Exception:
                            pass
                        await ws.send_json(
                            {
                                "type": "status",
                                "status": "fps_updated",
                                "fps": session.stream_fps,
                                "message": f"Stream rate set to {session.stream_fps} FPS.",
                            }
                        )

                except WebSocketDisconnect:
                    logger.info("Client WebSocket disconnected.")
                    break
                except Exception as e:
                    logger.debug(f"WebSocket loop message error: {e}")

        except Exception as e:
            logger.error(f"Screencast stream error: {e}")
            try:
                await ws.send_json({"type": "error", "message": str(e)})
            except Exception:
                pass
        finally:
            if monitor_task:
                monitor_task.cancel()
            if session.cancelled or session.saved or not session.ready:
                await self._cleanup(session)


stream_manager = SessionStreamManager()
