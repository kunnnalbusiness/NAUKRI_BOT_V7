"""
Access Denied & Security Checkpoint Detector for Naukri and LinkedIn.
Detects 403 Forbidden, datacenter IP reputation blocks, Cloudflare challenges,
LinkedIn security checkpoints, and Naukri auth walls.
Automatically pauses the engine and informs the user with actionable instructions.
"""

import os
import logging
from typing import Tuple, Optional, Any

logger = logging.getLogger("access_detector")

BLOCK_PATTERNS = [
    "access denied",
    "403 forbidden",
    "security verification",
    "verify you are human",
    "unusual activity",
    "temporarily blocked",
    "attention required! | cloudflare",
    "challenge-running",
    "cf-browser-verification",
    "authwall",
    "checkpoint/challenge",
    "checkpoint challenge",
]


def check_page_access_denied(
    page: Any, site: str = "general", response_status: Optional[int] = None
) -> Tuple[bool, str]:
    """
    Evaluates whether the current page is blocked by Access Denied, 403, or a security checkpoint.

    Returns:
        (is_blocked: bool, detailed_message: str)
    """
    is_cloud = os.environ.get("RENDER") is not None
    if response_status in (403, 429):
        if is_cloud:
            msg = (
                f"{site.title()} returned HTTP {response_status} (Access Denied). "
                f"Datacenter IP is blocked by {site.title()} security shield. "
                f"Local machine (India residential IP) se chalao ya session import karo."
            )
        else:
            msg = (
                f"{site.title()} returned HTTP {response_status} (Access Denied). "
                f"Anti-bot filter (Akamai) ne automated request ko block kiya hai. "
                f"Live Login karke session refresh karo ya session import karo."
            )
        logger.warning(f"[{site}] {msg}")
        return True, msg

    try:
        url = (page.url or "").lower()
        title = ""
        try:
            title = (page.title() or "").lower()
        except Exception:
            pass

        # Check URL indicators
        if "/checkpoint/" in url or "/challenge/" in url:
            msg = (
                f"{site.title()} security checkpoint encountered at {page.url}. "
                f"Naukri/LinkedIn ne verification challenge manga hai. "
                f"Live Login se solve karo ya session import karo."
            )
            logger.warning(f"[{site}] {msg}")
            return True, msg

        # Check Page Title indicators
        for pattern in BLOCK_PATTERNS:
            if pattern in title:
                if is_cloud:
                    msg = (
                        f"{site.title()} Access Denied detected (Page title: '{title}'). "
                        f"Naukri/LinkedIn ne datacenter IP/browser ko block kiya hai. "
                        f"Local machine (India residential IP) se chalao ya session import karo."
                    )
                else:
                    msg = (
                        f"{site.title()} Access Denied detected (Page title: '{title}'). "
                        f"Anti-bot protection ne browser ko flag kiya hai. "
                        f"Live Login se session refresh karo ya session import karo."
                    )
                logger.warning(f"[{site}] {msg}")
                return True, msg

        # Check body text snippet for explicit Access Denied header
        try:
            h1_text = page.evaluate(
                """() => {
                const h1 = document.querySelector('h1, h2, title, #challenge-error-title');
                return h1 ? h1.innerText.toLowerCase() : '';
            }"""
            )
            for pattern in BLOCK_PATTERNS:
                if pattern in h1_text:
                    if is_cloud:
                        msg = (
                            f"{site.title()} Access Denied detected ({h1_text}). "
                            f"Naukri/LinkedIn ne datacenter IP/browser ko block kiya hai. "
                            f"Local machine (India residential IP) se chalao ya session import karo."
                        )
                    else:
                        msg = (
                            f"{site.title()} Access Denied detected ({h1_text}). "
                            f"Anti-bot protection ne browser ko flag kiya hai. "
                            f"Live Login se session refresh karo ya session import karo."
                        )
                    logger.warning(f"[{site}] {msg}")
                    return True, msg
        except Exception:
            pass

    except Exception as e:
        logger.debug(f"Error checking access denied state: {e}")

    return False, ""


async def async_check_page_access_denied(
    page: Any, site: str = "general", response_status: Optional[int] = None
) -> Tuple[bool, str]:
    """
    Async version for async Playwright Page objects in session_manager.
    Evaluates whether the current page is blocked by Access Denied, 403, or a security checkpoint.
    """
    is_cloud = os.environ.get("RENDER") is not None
    if response_status in (403, 429):
        if is_cloud:
            msg = (
                f"{site.title()} returned HTTP {response_status} (Access Denied). "
                f"Datacenter IP is blocked by {site.title()} security shield. "
                f"Local machine (India residential IP) se chalao ya session import karo."
            )
        else:
            msg = (
                f"{site.title()} returned HTTP {response_status} (Access Denied). "
                f"Anti-bot filter (Akamai) ne automated request ko block kiya hai. "
                f"Live Login karke session refresh karo ya session import karo."
            )
        logger.warning(f"[{site}] {msg}")
        return True, msg

    try:
        url = (page.url or "").lower()
        title = ""
        try:
            t = await page.title()
            title = (t or "").lower()
        except Exception:
            pass

        # Check URL indicators
        if "/checkpoint/" in url or "/challenge/" in url:
            msg = (
                f"{site.title()} security checkpoint encountered at {page.url}. "
                f"Naukri/LinkedIn ne verification challenge manga hai. "
                f"Live Login se solve karo ya session import karo."
            )
            logger.warning(f"[{site}] {msg}")
            return True, msg

        # Check Page Title indicators
        for pattern in BLOCK_PATTERNS:
            if pattern in title:
                if is_cloud:
                    msg = (
                        f"{site.title()} Access Denied detected (Page title: '{title}'). "
                        f"Naukri/LinkedIn ne datacenter IP/browser ko block kiya hai. "
                        f"Local machine (India residential IP) se chalao ya session import karo."
                    )
                else:
                    msg = (
                        f"{site.title()} Access Denied detected (Page title: '{title}'). "
                        f"Anti-bot protection ne browser ko flag kiya hai. "
                        f"Live Login se session refresh karo ya session import karo."
                    )
                logger.warning(f"[{site}] {msg}")
                return True, msg

        # Check body text snippet for explicit Access Denied header
        try:
            h1_text = await page.evaluate(
                """() => {
                const h1 = document.querySelector('h1, h2, title, #challenge-error-title');
                return h1 ? h1.innerText.toLowerCase() : '';
            }"""
            )
            for pattern in BLOCK_PATTERNS:
                if pattern in h1_text:
                    if is_cloud:
                        msg = (
                            f"{site.title()} Access Denied detected ({h1_text}). "
                            f"Naukri/LinkedIn ne datacenter IP/browser ko block kiya hai. "
                            f"Local machine (India residential IP) se chalao ya session import karo."
                        )
                    else:
                        msg = (
                            f"{site.title()} Access Denied detected ({h1_text}). "
                            f"Anti-bot protection ne browser ko flag kiya hai. "
                            f"Live Login se session refresh karo ya session import karo."
                        )
                    logger.warning(f"[{site}] {msg}")
                    return True, msg
        except Exception:
            pass

    except Exception as e:
        logger.debug(f"Error checking access denied state: {e}")

    return False, ""
