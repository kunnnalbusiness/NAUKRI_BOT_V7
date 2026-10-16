"""
Comprehensive Test Suite for the 10-Minute Fresh Rule & Skip Logic.
Tests:
- Freshness relative strings ("Just now", "2m ago", "10 mins ago")
- Older relative strings ("11m ago", "2 hours ago", "yesterday", "3 days ago")
- ISO datetime tags evaluated against Asia/Kolkata timezone
- Unparseable date strings rejected with 'date unparseable'
- Configurable POSTED_WITHIN_MINUTES threshold
- Real skip logic rules: too old, already applied, no Easy Apply, unparseable date, fresh + Easy Apply = apply
"""

from datetime import datetime
from common.time_filter import is_job_within_age_limit, KOLKATA_TZ


def test_fresh_relative_strings():
    """Verify that postings <= 10 minutes are accepted as fresh."""
    fresh_samples = [
        "Just now",
        "Just Now",
        "Few seconds ago",
        "1 minute ago",
        "2 mins ago",
        "5m ago",
        "8 minutes ago",
        "10 mins ago",
        "10m ago",
        "few minutes ago",
    ]
    for sample in fresh_samples:
        is_ok, reason = is_job_within_age_limit(text=sample, max_minutes=10)
        assert is_ok is True, f"Expected '{sample}' to be fresh, got reason: {reason}"
        assert "fresh" in reason


def test_older_relative_strings_rejected():
    """Verify that postings > 10 minutes are rejected with 'older than 10 min'."""
    old_samples = [
        ("11 mins ago", "older than 10 min"),
        ("15m ago", "older than 10 min"),
        ("1 hour ago", "older than 10 min"),
        ("2 hours ago", "older than 10 min"),
        ("few hours ago", "older than 10 min"),
        ("yesterday", "older than 10 min"),
        ("1 day ago", "older than 10 min"),
        ("3 days ago", "older than 10 min"),
        ("1 week ago", "older than 10 min"),
        ("1 month ago", "older than 10 min"),
        (
            "Today",
            "older than 10 min",
        ),  # Generic 'Today' without minutes is treated as > 10m
    ]
    for sample, expected_substr in old_samples:
        is_ok, reason = is_job_within_age_limit(text=sample, max_minutes=10)
        assert is_ok is False, f"Expected '{sample}' to be rejected, got: {reason}"
        assert (
            expected_substr in reason
        ), f"Reason for '{sample}' was '{reason}', expected '{expected_substr}'"


def test_iso_datetime_attribute_parsing():
    """Verify ISO datetime parsing against Asia/Kolkata timezone."""
    # Fixed reference time: 2026-10-07 12:00:00 Asia/Kolkata
    ref_now = datetime(2026, 10, 7, 12, 0, 0, tzinfo=KOLKATA_TZ)

    # 1. Posted 4 minutes ago: 11:56:00 Kolkata
    iso_4m = "2026-10-07T11:56:00+05:30"
    is_ok, reason = is_job_within_age_limit(
        datetime_attr=iso_4m, max_minutes=10, now_dt=ref_now
    )
    assert is_ok is True
    assert "fresh" in reason

    # 2. Posted 4 minutes ago in UTC: 06:26:00 UTC == 11:56:00 Kolkata
    iso_utc_4m = "2026-10-07T06:26:00Z"
    is_ok, reason = is_job_within_age_limit(
        datetime_attr=iso_utc_4m, max_minutes=10, now_dt=ref_now
    )
    assert is_ok is True
    assert "fresh" in reason

    # 3. Posted 25 minutes ago in UTC: 06:05:00 UTC == 11:35:00 Kolkata
    iso_utc_25m = "2026-10-07T06:05:00Z"
    is_ok, reason = is_job_within_age_limit(
        datetime_attr=iso_utc_25m, max_minutes=10, now_dt=ref_now
    )
    assert is_ok is False
    assert "older than 10 min" in reason


def test_unparseable_date_rejected():
    """Verify that unparseable text is rejected with 'date unparseable' (never blind apply)."""
    unparseable_samples = [
        "",
        None,
        "Confidential Opening",
        "Immediate Joiner Required",
        "Not a real date string 123",
    ]
    for sample in unparseable_samples:
        is_ok, reason = is_job_within_age_limit(text=sample, max_minutes=10)
        assert is_ok is False
        assert "date unparseable" in reason


def test_custom_threshold_configuration(monkeypatch):
    """Verify threshold can be overridden via parameter or POSTED_WITHIN_MINUTES env var."""
    # With max_minutes = 20, 15m ago is fresh
    is_ok, _ = is_job_within_age_limit(text="15 mins ago", max_minutes=20)
    assert is_ok is True

    # With POSTED_WITHIN_MINUTES = 5 in env
    monkeypatch.setenv("POSTED_WITHIN_MINUTES", "5")
    is_ok_env, reason_env = is_job_within_age_limit(text="8 mins ago")
    assert is_ok_env is False
    assert "older than 5 min" in reason_env


def test_skip_rules_matrix():
    """
    Test real application skip rules:
    - Rule 1: Too old -> Skip ('older than 10 min')
    - Rule 2: Already applied -> Skip ('already applied')
    - Rule 3: No Easy Apply -> Skip ('External application only')
    - Rule 4: Unparseable date -> Skip ('date unparseable')
    - Rule 5: Fresh + Easy Apply + Not applied -> Apply (Pass)
    """

    def evaluate_job_candidate(card: dict, already_applied: set) -> tuple[str, str]:
        # 1. Deduplication / Already Applied
        job_id = card.get("job_id", "")
        if job_id in already_applied:
            return "skip", "already applied previously"

        # 2. Date Freshness
        is_fresh, fresh_reason = is_job_within_age_limit(
            text=card.get("posted_text"),
            datetime_attr=card.get("datetime_attr"),
            max_minutes=10,
        )
        if not is_fresh:
            return "skip", fresh_reason

        # 3. Easy Apply Check
        if not card.get("has_easy_apply", False):
            return "skip", "External application only (not Easy Apply)"

        return "apply", "ready to apply"

    applied_set = {"JOB-101"}

    # Case 1: Too old
    status, reason = evaluate_job_candidate(
        {"job_id": "JOB-102", "posted_text": "2 hours ago", "has_easy_apply": True},
        applied_set,
    )
    assert status == "skip"
    assert "older than 10 min" in reason

    # Case 2: Already applied
    status, reason = evaluate_job_candidate(
        {"job_id": "JOB-101", "posted_text": "2 mins ago", "has_easy_apply": True},
        applied_set,
    )
    assert status == "skip"
    assert "already applied" in reason

    # Case 3: No Easy Apply
    status, reason = evaluate_job_candidate(
        {"job_id": "JOB-103", "posted_text": "3 mins ago", "has_easy_apply": False},
        applied_set,
    )
    assert status == "skip"
    assert "not Easy Apply" in reason

    # Case 4: Unparseable date
    status, reason = evaluate_job_candidate(
        {"job_id": "JOB-104", "posted_text": "Some text", "has_easy_apply": True},
        applied_set,
    )
    assert status == "skip"
    assert "date unparseable" in reason

    # Case 5: Fresh + Easy Apply + Not yet applied -> MUST APPLY!
    status, reason = evaluate_job_candidate(
        {"job_id": "JOB-105", "posted_text": "Just now", "has_easy_apply": True},
        applied_set,
    )
    assert status == "apply"
    assert reason == "ready to apply"


def test_salary_and_metric_guard():
    """Verify that salaries like 2.2M INR/yr or metric counters are never mistaken for minutes."""
    salary_samples = [
        "2.2M INR/yr - 2.7M INR/yr",
        "Salary: 10M INR",
        "5M LPA",
        "2m followers",
        "10M members",
        "3.5M USD/year",
    ]
    for sample in salary_samples:
        is_ok, reason = is_job_within_age_limit(text=sample, max_minutes=10)
        assert (
            is_ok is False
        ), f"Expected '{sample}' to not pass as fresh minutes, got: {reason}"

    # Complex LinkedIn card text with salary AND old age
    complex_card_text = "Data Engineer SerkoBengaluru (Hybrid) 2.2M INR/yr - 2.7M INR/yr Viewed · Posted 1 month ago · Easy Apply"
    is_ok, reason = is_job_within_age_limit(text=complex_card_text, max_minutes=10)
    assert is_ok is False
    assert "older than 10 min" in reason

    # Shorthand LinkedIn tokens
    assert is_job_within_age_limit(text="2mo ago", max_minutes=10)[0] is False
    assert is_job_within_age_limit(text="1w ago", max_minutes=10)[0] is False
    assert is_job_within_age_limit(text="3d ago", max_minutes=10)[0] is False
    assert is_job_within_age_limit(text="2h ago", max_minutes=10)[0] is False
    assert is_job_within_age_limit(text="5m ago", max_minutes=10)[0] is True
    assert is_job_within_age_limit(text="2m", max_minutes=10)[0] is True
