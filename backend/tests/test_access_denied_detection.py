"""
Automated Test for Access Denied & Security Checkpoint Detection.
Verifies:
- Detection of 403 HTTP status code
- Detection of title indicators ('Access Denied', 'Attention Required! | Cloudflare')
- Detection of URL indicators ('/checkpoint/', '/challenge/')
- Detection of body text indicators ('Security Verification', 'Verify you are human')
- Actionable notification message instructing user to run locally on India residential IP or import session JSON.
"""

from common.access_detector import check_page_access_denied


class MockPage:
    def __init__(
        self, url="https://www.linkedin.com/feed", title="Feed | LinkedIn", h1_text=""
    ):
        self.url = url
        self._title = title
        self._h1 = h1_text

    def title(self):
        return self._title

    def evaluate(self, script):
        return self._h1


def test_http_403_access_denied():
    """Verify HTTP 403 immediately flags Access Denied with actionable guidance."""
    page = MockPage()
    is_blocked, msg = check_page_access_denied(page, site="naukri", response_status=403)
    assert is_blocked is True
    assert "Access Denied" in msg
    assert "India residential IP" in msg or "session import" in msg


def test_cloudflare_challenge_detection():
    """Verify Cloudflare verification page triggers detection."""
    page = MockPage(
        url="https://www.naukri.com/security",
        title="Attention Required! | Cloudflare",
        h1_text="Please verify you are human",
    )
    is_blocked, msg = check_page_access_denied(page, site="naukri")
    assert is_blocked is True
    assert "Access Denied detected" in msg


def test_linkedin_checkpoint_challenge_detection():
    """Verify LinkedIn /checkpoint/challenge URL triggers detection."""
    page = MockPage(
        url="https://www.linkedin.com/checkpoint/challenge/AZ123",
        title="Security Verification | LinkedIn",
    )
    is_blocked, msg = check_page_access_denied(page, site="linkedin")
    assert is_blocked is True
    assert "checkpoint encountered" in msg or "Access Denied" in msg


def test_clean_allowed_page():
    """Verify valid authenticated page does not trigger Access Denied."""
    page = MockPage(
        url="https://www.linkedin.com/feed/",
        title="LinkedIn Feed",
        h1_text="Welcome back",
    )
    is_blocked, msg = check_page_access_denied(
        page, site="linkedin", response_status=200
    )
    assert is_blocked is False
    assert msg == ""
