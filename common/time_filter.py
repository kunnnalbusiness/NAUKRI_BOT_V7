"""
Time Filter and Job Freshness Evaluator (The 10-Minute Rule).
Parses relative posting ages and ISO datetime timestamps against Asia/Kolkata timezone.
Ensures the autonomous bot ONLY applies to jobs posted within the configured threshold
(default 10 minutes), strictly rejecting older or unparseable jobs.
"""

import re
from datetime import datetime
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

KOLKATA_TZ = ZoneInfo("Asia/Kolkata")


def parse_posted_minutes(
    text: Optional[str] = None,
    datetime_attr: Optional[str] = None,
    now_dt: Optional[datetime] = None,
) -> Tuple[Optional[float], str]:
    """
    Parses a job posting age into minutes.
    Returns:
        (minutes_float, parse_mode_description) or (None, "unparseable_reason")
    """
    if now_dt is None:
        now_dt = datetime.now(KOLKATA_TZ)
    elif now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=KOLKATA_TZ)

    # 1. Try parsing explicit ISO datetime attribute first (e.g. from <time datetime="...">)
    if datetime_attr and datetime_attr.strip():
        attr_clean = datetime_attr.strip()
        try:
            # Handle ISO formats: 2026-10-07T06:15:00Z, 2026-10-07T11:45:00+05:30, etc.
            if attr_clean.endswith("Z"):
                parsed = datetime.fromisoformat(attr_clean[:-1] + "+00:00")
            else:
                parsed = datetime.fromisoformat(attr_clean)

            # Convert to Kolkata timezone
            parsed_kolkata = parsed.astimezone(KOLKATA_TZ)
            delta = now_dt - parsed_kolkata
            delta_mins = max(0.0, delta.total_seconds() / 60.0)
            return delta_mins, f"datetime_attr ({datetime_attr})"
        except Exception:
            pass

    # 2. Parse relative text string
    if not text or not str(text).strip():
        return None, "empty_date_text"

    raw = str(text).strip()
    s = raw.lower()

    # Instant / Just Now phrases
    if any(
        phrase in s
        for phrase in (
            "just now",
            "few seconds ago",
            "moment ago",
            "moments ago",
            "right now",
            "seconds ago",
            "sec ago",
            "0m ago",
        )
    ):
        return 0.0, f"relative ('{raw}')"

    # Weeks, Months, Years — MUST CHECK BEFORE MINUTES / HOURS TO PREVENT "1 month" / "2mo" / "1y" from being misread
    if any(
        unit in s
        for unit in (
            "month",
            "months",
            "year",
            "years",
            "30d+",
            "few weeks",
            "few months",
        )
    ):
        return 43200.0, f"relative_months_plus ('{raw}')"

    mo_match = re.search(r"(?<![\d.])\b(\d+)\s*(?:mo|mos)\b", s)
    if mo_match:
        try:
            mos = float(mo_match.group(1))
            return mos * 43200.0, f"relative_months ('{raw}')"
        except ValueError:
            pass

    w_match = re.search(r"(?<![\d.])\b(\d+)\s*(?:w|wk|wks|week|weeks)\b", s)
    if w_match:
        try:
            weeks = float(w_match.group(1))
            return weeks * 10080.0, f"relative_weeks ('{raw}')"
        except ValueError:
            pass

    # Explicit Days: e.g. "1 day ago", "yesterday", "2 days ago", "1d", "few days ago"
    if "yesterday" in s:
        return 24.0 * 60.0, "relative_yesterday"

    if "few day" in s:
        return 3.0 * 1440.0, f"relative_few_days ('{raw}')"

    d_match = re.search(r"(?<![\d.])\b(\d+)\s*(?:d|day|days)\b", s)
    if d_match:
        try:
            days = float(d_match.group(1))
            return days * 1440.0, f"relative_days ('{raw}')"
        except ValueError:
            pass

    # Explicit or Phrase Hours: e.g. "1 hour ago", "2 hours ago", "3h ago", "1h", "few hours ago"
    if "few hour" in s or "few hrs" in s:
        return 120.0, f"relative_few_hours ('{raw}')"

    h_match = re.search(r"(?<![\d.])\b(\d+)\s*(?:h|hr|hrs|hour|hours)\b", s)
    if h_match:
        try:
            hours = float(h_match.group(1))
            return hours * 60.0, f"relative_hours ('{raw}')"
        except ValueError:
            pass

    # Explicit Minutes: e.g. "5 mins ago", "1 minute ago", "10m", "3m ago", "8 min", "few minutes ago"
    if "few min" in s or "few minute" in s:
        return 3.0, f"relative_few_mins ('{raw}')"

    # Match minutes:
    # 1. Full word "min/mins/minute/minutes":
    m_match = re.search(r"(?<![\d.])\b(\d+)\s*(?:min|mins|minute|minutes)\b", s)
    # 2. Short form "m" or "m ago" — MUST NOT match salary/metrics like "2.2M", "5M INR", "10M LPA", "2m followers":
    if not m_match:
        m_match = re.search(
            r"(?<![\d.])\b(\d+)\s*m(?:\s*ago)?\b(?!\s*(?:inr|usd|eur|gbp|lpa|/yr|/year|per\s*year|annum|followers|members|views|downloads|connections))",
            s,
        )
    if m_match:
        try:
            mins = float(m_match.group(1))
            return mins, f"relative_mins ('{raw}')"
        except ValueError:
            pass

    # Generic "today" without specific minutes or hours:
    # If it just says "today" or "posted today", it cannot be confirmed <= 10 min.
    # We assign 60.0 minutes (1 hour) so it safely fails the 10-minute check unless detailed minutes are found.
    if s in ("today", "posted today", "posted: today"):
        return 60.0, f"relative_today_unspecified ('{raw}')"

    # 3. Try parsing standard date strings: e.g. "07 Oct 2026", "2026-10-07"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d %b %Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(raw, fmt).replace(tzinfo=KOLKATA_TZ)
            delta = now_dt - parsed
            delta_mins = max(0.0, delta.total_seconds() / 60.0)
            return delta_mins, f"parsed_date ({fmt})"
        except ValueError:
            continue

    return None, f"unrecognized_format ('{raw}')"


def is_job_within_age_limit(
    text: Optional[str] = None,
    datetime_attr: Optional[str] = None,
    max_minutes: Optional[int] = None,
    now_dt: Optional[datetime] = None,
) -> Tuple[bool, str]:
    """
    Evaluates whether a job posting satisfies the fresh rule.
    Defaults to POSTED_WITHIN_MINUTES from environment (or 10 minutes).

    Returns:
        (is_allowed: bool, reason: str)
        - If allowed: (True, "fresh (<age> min ago)")
        - If too old: (False, "older than <max_minutes> min (<age> min ago)")
        - If unparseable: (False, "date unparseable: <details>")
    """
    import os

    if max_minutes is None:
        try:
            max_minutes = int(os.getenv("POSTED_WITHIN_MINUTES", "10"))
        except Exception:
            max_minutes = 10

    mins, mode_info = parse_posted_minutes(text, datetime_attr, now_dt=now_dt)

    if mins is None:
        return False, f"date unparseable ({mode_info})"

    if mins <= float(max_minutes):
        return True, f"fresh ({mins:.1f}m ago <= {max_minutes}m)"

    return False, f"older than {max_minutes} min ({mins:.1f}m ago)"
