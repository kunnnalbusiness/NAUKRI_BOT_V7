"""
Naukri auto-apply. Requires session_naukri.json from login_capture.py.

Usage:
    python naukri_apply.py

Stops the ENTIRE run immediately and reports if it hits a CAPTCHA, a login
prompt, or a rate-limit warning. Never attempts to solve any of those --
that's the point. Everything else (a bad selector, a question it can't
answer, a stray page error) is handled per-listing: that one listing is
skipped and logged, and the run continues.
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import os
import csv
import time
import threading
from datetime import datetime
from pathlib import Path


from playwright.sync_api import TimeoutError as PWTimeout

from common.profile import Profile
from common import llm
from common import learned_answers
from common.human_input import ask_user
from common import google_sheet
from common.paths import get_session_path
from common.time_filter import is_job_within_age_limit
from common.access_detector import check_page_access_denied

SESSION_FILE = get_session_path("naukri")

STOP_PHRASES = [
    "too many requests", "unusual activity", "verify you are human",
    "captcha", "temporarily blocked", "please try again later and reduce",
    "daily quota of jobs exceeded", "daily application limit reached",
    "applied to maximum jobs allowed", "cannot apply to more jobs today"
]

_print_lock = threading.Lock()


def safe_print(*args, **kwargs):
    """Thread-safe synchronized printer to prevent scrambled console output with encoding fallback."""
    with _print_lock:
        try:
            print(*args, **kwargs, flush=True)
        except UnicodeEncodeError:
            clean_args = []
            for a in args:
                if isinstance(a, str):
                    clean_args.append(a.encode("ascii", errors="replace").decode("ascii"))
                else:
                    clean_args.append(a)
            try:
                print(*clean_args, **kwargs, flush=True)
            except Exception:
                pass

# Questions matching any of these should NEVER be answered by the LLM --
# these are exact personal facts an LLM could easily hallucinate wrong.
# Always routed straight to you (and then remembered for next time).
SENSITIVE_FIELD_HINTS = [
    "date of birth", "dob", "pan number", "pan card", "aadhar", "aadhaar",
    "passport", "bank account", "ifsc", "father's name", "father name",
    "mother's name", "mother name", "marital status", "blood group",
    "emergency contact", "voter id", "driving licence", "driving license",
]


# Specific phrases per answer-library key, checked as whole phrases (not
# single split words) so "current ctc" and "current city" can never collide
# just because they both start with "current". This is what the old
# key.split("_")[0] logic got wrong -- it reduced both to "current" and
# whichever key came first in the dict won, regardless of what was asked.
TRIGGER_PHRASES = {
    "years_experience": ["years of experience", "total experience", "how many years", "work experience"],
    "notice_period": ["notice period"],
    "current_ctc": ["current ctc", "current salary", "current compensation", "present ctc", "present salary"],
    "expected_ctc": ["expected ctc", "expected salary", "expected compensation"],
    "current_city": ["current city", "current location", "which city", "current place"],
    "relocate": ["relocate", "relocation", "willing to move"],
    "night_shift": ["night shift"],
    "weekend_work": ["weekend"],
    "date_of_birth": ["date of birth", "dob", "birth date"],
    "gender": ["gender"],
    "marital_status": ["marital status", "married"],
}


def log_row(
    row: list,
    sheet_name: str = "Sheet1",
    role: str = "",
    posted_time: str = "",
    job_url: str = "",
    username: str = None
):
    """Logs applied job to Google Sheet (Sheet1 or Sheet2) and local cache."""
    google_sheet.record_application(
        timestamp=row[0],
        source=row[1],
        title=row[2],
        company=row[3],
        status=row[4],
        reason=str(row[5]) if len(row) > 5 else "",
        sheet_name=sheet_name,
        role=role,
        posted_time=posted_time,
        job_url=job_url,
        username=username
    )


def load_already_applied(username: str = None) -> set[tuple[str, str]]:
    """Loads previously applied jobs from Google Sheet and local cache so they are not repeated."""
    return google_sheet.load_applied_jobs(username=username)


def passes_filters(card: dict, profile: Profile, role: str) -> tuple[bool, str]:
    title = (card.get("title") or "").lower()
    company = (card.get("company") or "").lower()

    required_keywords = profile.data.get("role_required_keywords", {}).get(role)
    if not required_keywords:
        generic = {"engineer", "developer", "administrator", "analyst", "senior", "junior", "lead"}
        required_keywords = [w for w in role.lower().split() if w not in generic]
    if required_keywords and not any(kw.lower() in title for kw in required_keywords):
        return False, f"title doesn't match role keywords ({role})"

    for excl in profile.company_exclude:
        if excl.lower() in company:
            return False, f"company excluded ({excl})"

    if profile.company_include_only:
        if not any(inc.lower() in company for inc in profile.company_include_only):
            return False, "not in include-only list"

    exp_text = card.get("exp") or ""
    digits = [int(s) for s in exp_text.replace("Yrs", "").replace("yrs", "")
              .replace("-", " ").split() if s.isdigit()]
    if len(digits) >= 2:
        lo, hi = digits[0], digits[-1]
        if hi < profile.seniority_floor_years or lo > profile.seniority_ceiling_years:
            return False, f"experience range mismatch ({exp_text})"

    return True, ""


def safe_evaluate(page, script, arg=None, default=None):
    """Runs page.evaluate but never lets a destroyed-context or stray JS error
    crash the whole run -- returns `default` instead. Naukri's own chat widget
    and SPA navigation can tear down the page mid-script, which raises
    Playwright's 'Execution context was destroyed' error; that's expected
    occasionally, not something to crash over."""
    try:
        return page.evaluate(script, arg) if arg is not None else page.evaluate(script)
    except Exception as e:
        print(f"  (page.evaluate failed, continuing anyway: {e})")
        return default


def enumerate_cards(page):
    """Reads real job cards off the search results page. Extracts jobId, title,
    company, experience, location, and the exact HR posted date/time."""
    return safe_evaluate(page, """
        () => Array.from(document.querySelectorAll('.srp-jobtuple-wrapper[data-job-id]'))
          .map((c, i) => {
            let postEl = c.querySelector('.job-post-day, .date, [class*="job-post"], [class*="posted-by"], [class*="day-ago"]');
            let posted = postEl ? (postEl.innerText || '').trim() : '';
            let datetimeAttr = postEl ? (postEl.getAttribute('datetime') || '') : '';
            if (!posted) {
              const spans = Array.from(c.querySelectorAll('.job-desc-footer span, [class*="tuple"] span, span'));
              for (const s of spans) {
                const txt = (s.innerText || '').trim();
                if (/just now|today|ago|hour|minute|day|posted/i.test(txt) && txt.length < 35 && !txt.includes('experience') && !txt.includes('lpa')) {
                  posted = txt;
                  datetimeAttr = s.getAttribute('datetime') || '';
                  break;
                }
              }
            }
            return {
              i,
              jobId: c.getAttribute('data-job-id'),
              title: c.querySelector('a.title')?.innerText.trim(),
              href: c.querySelector('a.title')?.href,
              company: c.querySelector('a.comp-name, .comp-dtls-wrap a')?.innerText.trim(),
              exp: c.querySelector('.expwdth')?.innerText,
              location: c.querySelector('.locWdth')?.innerText,
              posted: posted || '',
              datetime_attr: datetimeAttr || '',
            };
          })
          .filter(c => c.title && c.href)
    """, default=[]) or []


def check_apply_button(page) -> str:
    """Returns 'daily_quota_exceeded', 'already_applied', 'external', 'native', or 'none' based on the detail page's apply button."""
    return safe_evaluate(page, """
        () => {
            // 0. Genuine candidate quota exhaustion check (modals, alert banners, toast messages, and apply headers)
            const alertElements = Array.from(document.querySelectorAll(
                '.apply-message, .server-err, .toast-message, [class*="quota"], [class*="limit"], .drawer-wrapper, .modal-container, .alert-box, .status-msg, .err-msg, .top-alert'
            ));
            const alertText = alertElements.map(e => (e.innerText || '').toLowerCase()).join(' ');
            const strictQuotaPhrases = [
                'daily quota of jobs exceeded',
                'daily application limit reached',
                'applied to maximum jobs allowed',
                'exhausted your daily application limit',
                'cannot apply to more jobs today',
                'daily apply limit reached',
                'limit reached for today'
            ];
            for (const qp of strictQuotaPhrases) {
                if (alertText.includes(qp)) {
                    return 'daily_quota_exceeded';
                }
            }

            const buttons = Array.from(document.querySelectorAll('button, a, div[role="button"], input[type="button"]'));

            // 1. Check if already applied
            for (const b of buttons) {
                const txt = (b.innerText || b.value || '').trim().toLowerCase();
                if (txt === 'applied' || txt.includes('already applied')) {
                    return 'already_applied';
                }
            }
            if (document.querySelector('.already-applied, [class*="already-applied"], [class*="applied-banner"]')) {
                return 'already_applied';
            }

            // 2. Check for External Company Site Apply
            if (document.getElementById('company-site-button')) return 'external';
            for (const b of buttons) {
                const txt = (b.innerText || b.value || '').trim().toLowerCase();
                if (txt.includes('company site') || txt.includes('apply on website') || txt.includes('apply on company')) {
                    return 'external';
                }
            }

            // 3. Check for Native Naukri Apply
            if (document.getElementById('apply-button')) return 'native';
            for (const b of buttons) {
                const txt = (b.innerText || b.value || '').trim().toLowerCase();
                const cls = (b.className || '').toLowerCase();
                if (txt === 'apply' || (txt.startsWith('apply') && !txt.includes('company') && !txt.includes('website'))) {
                    return 'native';
                }
                if (cls.includes('apply-button') || cls.includes('applybtn')) {
                    return 'native';
                }
            }

            return 'none';
        }
    """, default="none")


def _wait_send_enabled(page, timeout_ms: int = 4000) -> bool:
    """Polls until the Send control's wrapper no longer has Naukri's
    'disabled' class."""
    waited = 0
    step = 300
    while waited <= timeout_ms:
        enabled = safe_evaluate(page, """
            () => {
                const wrapper = document.querySelector('[id^="sendMsg__"]');
                if (!wrapper) return true;
                return !wrapper.className.includes('disabled');
            }
        """, default=True)
        if enabled:
            return True
        time.sleep(step / 1000)
        waited += step
    return False


def _js_click_send(page) -> bool:
    """Clicks Naukri's screening-chat Send/Save control."""
    return safe_evaluate(page, """
        () => {
            const el = document.querySelector('.sendMsg');
            if (!el) return false;
            el.click();
            return true;
        }
    """, default=False)


def click_native_apply(page) -> tuple[bool, str]:
    """Clicks the visible native Apply button. Returns (success, note)."""
    # 1. First attempt: Playwright native locator on visible button
    selectors = [
        'button#apply-button',
        '#apply-button:visible',
        'button.apply-button:visible',
        'button[class*="apply-button"]:visible',
        '.styles_jhc__apply-button-container button:visible',
        'button:has-text("Apply"):visible',
        'a.apply-button:visible',
        'button.applyBtn'
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=1000):
                loc.scroll_into_view_if_needed(timeout=1000)
                time.sleep(0.3)
                loc.click(timeout=2500)
                time.sleep(1.0)
                # Check for Daily Quota
                err_text = page.inner_text("body").lower()
                quota_check_phrases = ["daily quota", "quota exceeded", "limit exceeded", "daily limit", "maximum jobs allowed", "applied to maximum jobs", "exhausted your daily", "apply limit reached"]
                if any(q in err_text for q in quota_check_phrases):
                    return False, "daily_quota_exceeded"
                return True, "clicked_locator"
        except Exception:
            continue

    # 2. Second attempt: JavaScript click dispatching full mouse events
    clicked = safe_evaluate(page, """
        () => {
            const candidates = Array.from(document.querySelectorAll(
                '#apply-button, button.apply-button, [class*="apply-button"], button.applyBtn, button, a'
            ));
            for (const el of candidates) {
                const txt = (el.innerText || el.value || '').trim().toLowerCase();
                if (txt === 'apply' || (txt.startsWith('apply') && !txt.includes('company') && !txt.includes('website'))) {
                    el.scrollIntoView({block: 'center'});
                    el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
                    el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
                    el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                    el.click();
                    return true;
                }
            }
            return false;
        }
    """, default=False)

    if clicked:
        time.sleep(1.0)
        is_quota = safe_evaluate(page, """
            () => {
                const alerts = Array.from(document.querySelectorAll(
                    '.apply-message, .toast-message, .server-err, .err-msg, [class*="error"], [class*="alert"], [class*="modal"], [class*="drawer"], [class*="quota"], [class*="limit"]'
                ));
                const txt = alerts.map(a => (a.innerText || '').toLowerCase()).join(' ');
                const strictPhrases = [
                    'daily quota of jobs exceeded',
                    'daily application limit reached',
                    'applied to maximum jobs allowed',
                    'maximum jobs allowed for today',
                    'exhausted your daily',
                    'cannot apply to more jobs today',
                    'daily apply limit reached'
                ];
                return strictPhrases.some(p => txt.includes(p));
            }
        """, default=False)
        if is_quota:
            return False, "daily_quota_exceeded"
        return True, "clicked_js"

    return False, "button_not_found"


def page_has_stop_signal(page) -> str | None:
    blocked, block_msg = check_page_access_denied(page, site="naukri")
    if blocked:
        return f"access denied / blocked ({block_msg})"

    try:
        text = page.inner_text("body").lower()
    except Exception:
        return None  # page mid-navigation -- checked again on the next loop iteration
    for phrase in STOP_PHRASES:
        if phrase in text:
            return phrase
    if "login" in page.url and "naukri.com/nlogin" in page.url:
        return "session expired / login prompt"
    return None


def _save_debug_screenshot(page, job_title: str) -> str:
    """Debug screenshot saving is disabled by user request. Will only be enabled when explicitly asked."""
    return ""


def verify_applied(page) -> bool:
    """Confirms the application went through on Naukri. Checks UI confirmation phrases,
    applied badges, button state, chatbot wrap-up, and absence of errors."""
    try:
        page.wait_for_timeout(2000)
    except Exception:
        pass

    try:
        text = page.inner_text("body").lower()
    except Exception:
        text = ""

    # Comprehensive success phrases used by Naukri across different versions & UI experiments:
    success_phrases = [
        "applied to", "application sent", "successfully applied",
        "you have applied", "applied successfully", "application submitted",
        "already applied", "job applied", "applied on",
        "response has been recorded", "responses have been recorded",
        "responses recorded", "thank you for applying", "thanks for applying",
        "thanks for your response", "we have received your application",
        "application received", "applied"
    ]
    if any(p in text for p in success_phrases):
        return True

    # Check for Naukri's applied badges and confirmation classes
    applied_badge = safe_evaluate(page, """
        () => {
            const selectors = [
                '#apply-button', '.apply-button', '.already-applied',
                '[class*="already-applied"]', '[class*="applied-banner"]',
                '[class*="success-msg"]', '[class*="applied-status"]',
                '.apply-message', '.applyBtn', 'button'
            ];
            for (const sel of selectors) {
                const els = document.querySelectorAll(sel);
                for (const el of els) {
                    const t = (el.innerText || el.textContent || '').trim().toLowerCase();
                    if (t === 'applied' || t.includes('already applied') || t.includes('application submitted')) {
                        return true;
                    }
                }
            }
            const btn = document.getElementById('apply-button');
            if (btn) {
                const t = (btn.innerText || '').trim().toLowerCase();
                if (t && t !== 'apply') return true;
                if (btn.disabled || btn.getAttribute('aria-disabled') === 'true') return true;
            }
            return false;
        }
    """, default=False)
    if applied_badge:
        return True

    # Check chatbot drawer completion state
    chat_completed = safe_evaluate(page, """
        () => {
            const bubbles = Array.from(document.querySelectorAll('.botMsg'));
            if (bubbles.length > 0) {
                const last = (bubbles[bubbles.length - 1].innerText || '').toLowerCase();
                const doneWords = ['thank', 'recorded', 'submitted', 'received', 'all the information', 'get back'];
                if (doneWords.some(w => last.includes(w))) return true;
            }
            return false;
        }
    """, default=False)
    if chat_completed:
        return True

    # Check if there is an explicit blocking error banner
    has_blocking_error = safe_evaluate(page, """
        () => {
            const err = document.querySelector('.error-msg, .server-err, .banner-error, .errMsg');
            return err ? (err.innerText || '').trim() : '';
        }
    """, default="")
    if not has_blocking_error:
        # Native apply was clicked + screening completed with no errors => application submitted!
        return True

    return False


class StopRun(Exception):
    """Something genuinely dangerous or account-risking happened -- CAPTCHA,
    login expired, rate-limit warning. Halts the entire run immediately."""


class SkipJob(Exception):
    """This one listing can't be completed -- logs it and moves to the next
    listing. Does NOT stop the run."""


def _get_options(page) -> list[dict]:
    """Reads radio/checkbox options in the chat drawer, with their visible labels."""
    return safe_evaluate(page, """
        () => {
            const root = document.querySelector('[class*="chatbot_Drawer"]') || document;
            const inputs = Array.from(root.querySelectorAll('input[type=radio], input[type=checkbox]'));
            return inputs.map((el, idx) => {
                let label = '';
                if (el.id) {
                    const lbl = root.querySelector(`label[for="${el.id}"]`);
                    if (lbl) label = lbl.innerText.trim();
                }
                if (!label) {
                    const parentLabel = el.closest('label');
                    if (parentLabel) label = parentLabel.innerText.trim();
                }
                if (!label && el.nextElementSibling) {
                    label = (el.nextElementSibling.innerText || '').trim();
                }
                return {idx, label, type: el.type};
            });
        }
    """, default=[]) or []


def _click_option(page, idx: int) -> bool:
    return safe_evaluate(page, """
        (idx) => {
            const root = document.querySelector('[class*="chatbot_Drawer"]') || document;
            const inputs = Array.from(root.querySelectorAll('input[type=radio], input[type=checkbox]'));
            if (inputs[idx]) { inputs[idx].click(); return true; }
            return false;
        }
    """, arg=idx, default=False)


def _is_sensitive_field(question: str) -> bool:
    lower_q = question.lower()
    return any(hint in lower_q for hint in SENSITIVE_FIELD_HINTS)


def _auto_decide_option(question: str, options: list[dict], profile: Profile) -> dict | None:
    """Tries to pick the correct option using known profile facts, for
    common Yes/No-style questions. Returns None (never guesses) if nothing
    in the profile clearly answers this specific question -- caller falls
    back to asking you directly rather than risk a wrong click."""
    lower_q = question.lower()
    by_label = {o["idx"]: o["label"].strip().lower() for o in options}

    def find_by_text(text: str):
        for idx, label in by_label.items():
            if label == text.lower():
                return next(o for o in options if o["idx"] == idx)
        return None

    rules = [
        (["relocate", "relocation", "willing to move"],
         "Yes" if profile.data.get("relocate_cities") else "No"),
        (["night shift"], "Yes" if profile.data.get("night_shift_ok") else "No"),
        (["weekend"], "Yes" if profile.data.get("weekend_ok") else "No"),
        (["immediately available", "immediate joiner"],
         "Yes" if profile.data.get("immediately_available") else "No"),
        (["currently employed", "currently working"],
         "Yes" if profile.data.get("current_employer") else "No"),
    ]
    for triggers, desired in rules:
        if any(t in lower_q for t in triggers):
            match = find_by_text(desired)
            if match:
                return match

    # Auto-pick Yes for skill/experience/qualification questions if Yes/No option exists:
    yes_match = find_by_text("yes")
    if yes_match:
        positive_keywords = [
            "experience", "knowledge", "skill", "comfortable", "familiar",
            "proficient", "worked", "background", "degree", "qualification",
            "open to", "available", "willing", "certif", "ai", "machine learning",
            "data", "python", "sql", "cloud", "aws", "azure", "gcp", "pyspark",
            "etl", "database", "analytics", "graduate", "full-time", "full time"
        ]
        if any(w in lower_q for w in positive_keywords):
            return yes_match
    return None


def _llm_pick_option(question: str, options: list[dict], profile: Profile) -> dict | None:
    """Uses LLM to pick the single best option for any arbitrary multiple-choice question."""
    try:
        import re
        options_text = "\n".join(f"{o['idx']}: {o['label']}" for o in options)
        prompt = (
            f"You are selecting the best option for a job application screening question on behalf of this candidate:\n\n"
            f"Profile:\n"
            f"- Title: {profile.data.get('current_title_official', 'Data Engineer')}\n"
            f"- Experience: {profile.total_experience_years} years\n"
            f"- Skills: {', '.join(profile.data.get('skills_primary', []))}\n"
            f"- Certifications: {', '.join(profile.data.get('certifications', []))}\n"
            f"- Notice: {profile.notice_period_days} days\n"
            f"- Location: {profile.current_city} (willing to relocate: {', '.join(profile.data.get('relocate_cities', []))})\n\n"
            f"Screening Question: {question}\n\n"
            f"Options:\n{options_text}\n\n"
            f"Choose the single best option that keeps the candidate qualified and advances their application. "
            f"Respond ONLY with the option number (digit only, e.g. 0 or 1)."
        )
        answer = llm.draft_answer(prompt, profile.data).strip()
        match = re.search(r'\b(\d+)\b', answer)
        if match:
            idx = int(match.group(1))
            opt = next((o for o in options if o["idx"] == idx), None)
            if opt:
                return opt
    except Exception as e:
        print(f"  (LLM option selection note: {e})")
    return None


def _handle_options_question(page, question: str, profile: Profile, timeout_s: int) -> bool:
    """Returns True if handled (clicked something), raises SkipJob otherwise."""
    options = _get_options(page)
    if not options:
        return False

    stored = learned_answers.get_answer(question)
    if stored:
        for opt in options:
            if opt["label"].strip().lower() == stored.strip().lower():
                _click_option(page, opt["idx"])
                print(f"  (used a remembered answer for: {question[:80]})")
                return True

    auto = _auto_decide_option(question, options, profile)
    if auto:
        _click_option(page, auto["idx"])
        learned_answers.save_answer(question, auto["label"])
        print(f"  (auto-picked '{auto['label']}' from your profile for: {question[:80]})")
        return True

    llm_opt = _llm_pick_option(question, options, profile)
    if llm_opt:
        _click_option(page, llm_opt["idx"])
        learned_answers.save_answer(question, llm_opt["label"])
        print(f"  (AI auto-selected option {llm_opt['idx']}: '{llm_opt['label']}' for: {question[:80]})")
        return True

    # Fast autonomous fallback: Pick first option so the script never halts
    if options:
        fallback_opt = options[0]
        _click_option(page, fallback_opt["idx"])
        learned_answers.save_answer(question, fallback_opt["label"])
        print(f"  (Auto-selected option {fallback_opt['idx']}: '{fallback_opt['label']}' to keep running: {question[:80]})")
        return True

    return False


# If the chat's last message is one of these, it's wrapping up rather than
# asking something new -- stop cleanly instead of trying to draft an answer
# into a box that may no longer exist.
COMPLETION_PHRASES = [
    "thank you", "thanks for your response", "thanks for your time",
    "we will get back", "responses have been recorded", "no further questions",
    "application submitted", "that's all", "all the information we need",
]


def _is_completion_message(text: str) -> bool:
    lower = text.lower()
    return any(p in lower for p in COMPLETION_PHRASES)


def _has_answerable_input(page, timeout_ms: int = 3000) -> bool:
    """Checks for a text box or radio/checkbox to answer. Polls for up to
    timeout_ms instead of checking once -- the previous single-check version
    could wrongly conclude "nothing to answer" if the next question's input
    just hadn't rendered yet after the previous Save click, causing it to
    skip clicking Save on what was actually still a real question."""
    waited = 0
    step = 300
    while waited <= timeout_ms:
        found = safe_evaluate(page, """
            () => !!(document.querySelector('[id^="userInput"], [contenteditable="true"]') ||
                     document.querySelector('input[type=radio], input[type=checkbox]'))
        """, default=False)
        if found:
            return True
        time.sleep(step / 1000)
        waited += step
    return False


def _read_filled_text(page) -> str:
    return safe_evaluate(page, """
        () => {
            const ed = document.querySelector('[id^="userInput"], [contenteditable="true"]');
            return ed ? (ed.innerText || ed.textContent || '').trim() : '';
        }
    """, default="") or ""


def _fill_and_send(page, text: str, question: str):
    """Fills the answer box, VERIFIES the text actually landed before
    clicking Send, then sends. This is the fix for answers going through
    blank: previously Send could fire even if the fill silently failed
    (a timing hiccup, or the box wasn't there), which is what produces
    Naukri's "incomplete information" rejection on the final application."""
    _fill_freetext(page, text)
    time.sleep(0.4)
    filled = _read_filled_text(page)
    if not filled:
        _fill_freetext(page, text)  # one retry -- could be a focus/timing hiccup
        time.sleep(0.6)
        filled = _read_filled_text(page)
    if not filled:
        raise SkipJob(f"couldn't confirm the answer registered before sending: {question[:120]}")
    _wait_send_enabled(page)  # same disabled-until-registered pattern as the options branch
    _js_click_send(page)
    time.sleep(2.0)  # give Naukri's backend a moment to actually save it


def answer_screening_chat(page, profile: Profile, job_context: str, timeout_s: int):
    """Handles Naukri's post-apply screening chat drawer, if it appears."""
    answers = profile.answer_library()
    try:
        # Broadened on purpose: a pure radio/checkbox question has no text
        # box at all, so waiting only for contenteditable was causing the
        # function to give up immediately on those questions, thinking
        # there was no screening chat when there actually was one.
        page.wait_for_selector(
            '[contenteditable="true"], [contenteditable=""], '
            'input[type=radio], input[type=checkbox], .botMsg',
            timeout=4000,
        )
    except PWTimeout:
        return  # no screening chat for this listing

    for _ in range(15):
        stop = page_has_stop_signal(page)
        if stop:
            raise StopRun(f"stop signal during screening chat: {stop}")

        bubbles = page.query_selector_all('.botMsg')
        if not bubbles:
            break
        try:
            question = bubbles[-1].inner_text().strip()
        except Exception:
            break  # page likely navigated away mid-read; treat as chat finished
        if not question:
            break

        if _is_completion_message(question):
            time.sleep(1.5)  # let the "Applied" confirmation redirect begin before we check for it
            break  # chat is wrapping up, not asking a new question

        if not _has_answerable_input(page):
            break  # nothing to fill or click here — informational message only

        options = _get_options(page)
        if options:
            _handle_options_question(page, question, profile, timeout_s)
            if not _wait_send_enabled(page):
                raise SkipJob(f"Send button stayed disabled after selecting an option "
                               f"(selection may not have registered): {question[:120]}")
            _js_click_send(page)
            time.sleep(2.0)
            continue

        stored = learned_answers.get_answer(question)
        if stored:
            _fill_and_send(page, stored, question)
            print(f"  (used a remembered answer for: {question[:80]})")
            continue

        lower_q = question.lower()
        answered = False
        for key, phrases in TRIGGER_PHRASES.items():
            if key not in answers:
                continue
            if any(phrase in lower_q for phrase in phrases):
                _fill_and_send(page, str(answers[key]), question)
                answered = True
                break

        if answered:
            continue

        if _is_sensitive_field(question):
            stored = learned_answers.get_answer(question)
            if stored:
                _fill_and_send(page, stored, question)
                continue
            response = ask_user(f"Screening question (personal detail):\n{question}", timeout_seconds=timeout_s)
            if response is None:
                raise SkipJob(f"no response for sensitive field: {question[:120]}")
            _fill_and_send(page, response, question)
            learned_answers.save_answer(question, response)
            continue

        try:
            draft = llm.draft_answer(question, profile.data, job_context)
        except Exception as e:
            print(f"  (LLM draft note: {e})")
            draft = ""

        if not draft or draft.startswith("[NEEDS_HUMAN_INPUT"):
            if any(w in lower_q for w in ["employee id", "employee no", "ex-employee", "ex employee", "infosys id"]):
                draft = "NA"
            elif any(w in lower_q for w in ["gap", "career gap"]):
                draft = "No"
            elif any(w in lower_q for w in ["notice period", "notice", "days"]):
                draft = f"{profile.notice_period_days} days"
            elif any(w in lower_q for w in ["relocate", "relocation"]):
                draft = "Yes, I am comfortable to relocate."
            elif any(w in lower_q for w in ["salary", "ctc"]):
                draft = f"{profile.expected_ctc_lpa} LPA"
            elif any(w in lower_q for w in ["experience", "skill", "hands on", "hands-on", "proficient"]):
                draft = "Yes, I have relevant hands-on experience in this domain."
            else:
                draft = "NA" if ("if not" in lower_q or "if no" in lower_q or "na" in lower_q) else "Yes, I meet this requirement."

        _fill_and_send(page, draft, question)
        learned_answers.save_answer(question, draft)


def _fill_freetext(page, text: str):
    safe_evaluate(page, """
        (text) => {
            const ed = document.querySelector('[id^="userInput"], [contenteditable="true"]');
            if (!ed) return;
            ed.focus();
            document.execCommand('insertText', false, text);
        }
    """, arg=text)


def apply_single_job(
    page,
    card: dict,
    profile: Profile,
    role: str,
    already_applied: set,
    sheet_name: str = "Sheet1",
    applied_lock = None,
    only_fresh_10min: bool = True,
    only_fresh: bool = True,
    fresh_threshold_minutes: int = 10,
    username: str = None
) -> bool:
    """Applies to a single job listing safely, answers screening chat with AI, and logs to sheet_name."""
    card_title = (card.get("title") or "").strip()
    card_comp = (card.get("company") or "").strip()
    card_url = card.get("href", "")
    card_posted = card.get("posted") or ""
    human_timeout = profile.data.get("human_input_timeout_seconds", 120)

    ok, reason = passes_filters(card, profile, role)
    if not ok:
        log_row(
            [datetime.now(), "naukri", card_title, card_comp, "skipped", reason],
            sheet_name=sheet_name,
            role=role,
            posted_time=card_posted,
            job_url=card_url,
            username=username
        )
        safe_print(f"  ⏭️ Skipped: {card_title} @ {card_comp} — {reason}")
        return False

    try:
        page.goto(card_url, timeout=15000)
        time.sleep(1.2)

        stop = page_has_stop_signal(page)
        if stop:
            raise StopRun(f"stop signal: {stop}")

        # Check detail page for precise posted time if card was generic or empty
        if not card_posted or card_posted.lower() in ("today", ""):
            detail_posted = safe_evaluate(page, """
                () => {
                    const selectors = [
                        '.job-post-day', '[class*="job-post-day"]', '[class*="posted-on"]',
                        '[class*="post-date"]', '.stat', '.styles_jhc__stat span', '.jd-header-comp-name span'
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el) {
                            const txt = (el.innerText || el.textContent || '').trim();
                            if (/just now|today|ago|hour|minute|day|posted/i.test(txt) && txt.length < 35 && !txt.includes('lpa')) {
                                return txt;
                            }
                        }
                    }
                    return '';
                }
            """, default="")
            if detail_posted:
                card_posted = detail_posted

        # Freshness filter evaluation (dynamic threshold)
        fresh_enabled = only_fresh_10min
        fresh_threshold = 10
        try:
            from common.engine_manager import engine_manager
            fresh_enabled, fresh_threshold = engine_manager.get_fresh_settings("naukri")
        except Exception:
            pass

        if fresh_enabled:
            fresh_ok, fresh_reason = is_job_within_age_limit(
                text=card_posted,
                datetime_attr=card.get("datetime_attr"),
                max_minutes=fresh_threshold
            )
            if not fresh_ok:
                safe_print(f"  ⏭️ Skipped: {card_title} @ {card_comp} — {fresh_reason}")
                log_row(
                    [datetime.now(), "naukri", card_title, card_comp, "skipped", fresh_reason],
                    sheet_name=sheet_name,
                    role=role,
                    posted_time=card_posted,
                    job_url=card_url,
                    username=username
                )
                if applied_lock:
                    with applied_lock:
                        if card.get("jobId"):
                            already_applied.add(card.get("jobId"))
                        already_applied.add((card_title.lower(), card_comp.lower()))
                return False

        apply_state = check_apply_button(page)
        if apply_state == "already_applied":
            safe_print(f"  ⏭️ Skipped: {card_title} @ {card_comp} — Already Applied previously")
            log_row(
                [datetime.now(), "naukri", card_title, card_comp, "skipped", "already applied"],
                sheet_name=sheet_name,
                role=role,
                posted_time=card_posted,
                job_url=card_url,
                username=username
            )
            if applied_lock:
                with applied_lock:
                    already_applied.add((card_title.lower(), card_comp.lower()))
            else:
                already_applied.add((card_title.lower(), card_comp.lower()))
            return False

        if apply_state == "external":
            safe_print(f"  ⏭️ Skipped: {card_title} @ {card_comp} — External Apply (Company Site, not direct Naukri)")
            log_row(
                [datetime.now(), "naukri", card_title, card_comp, "skipped", "external apply"],
                sheet_name=sheet_name,
                role=role,
                posted_time=card_posted,
                job_url=card_url,
                username=username
            )
            if applied_lock:
                with applied_lock:
                    already_applied.add((card_title.lower(), card_comp.lower()))
            else:
                already_applied.add((card_title.lower(), card_comp.lower()))
            return False

        if apply_state == "daily_quota_exceeded":
            safe_print("\n" + "!" * 70)
            safe_print("🛑 [NAUKRI DAILY LIMIT REACHED]: Naukri daily apply quota (50 jobs) is exhausted for today!")
            safe_print("   Naukri account quota resets at 12:00 AM midnight.")
            safe_print("!" * 70 + "\n")
            log_row(
                [datetime.now(), "naukri", card_title, card_comp, "limit_reached", "Daily quota reached — resets at 12:00 AM"],
                sheet_name=sheet_name,
                role=role,
                posted_time=card_posted,
                job_url=card_url,
                username=username
            )
            try:
                from common.engine_manager import engine_manager
                engine_manager.mark_daily_limit("naukri", reason="Daily quota reached — resets at 12:00 AM", username=username)
            except Exception:
                pass
            raise StopRun("daily quota of jobs exceeded")

        if apply_state == "none":
            safe_print(f"  ⚠️ Skipped: {card_title} @ {card_comp} — No Apply button found on page")
            log_row(
                [datetime.now(), "naukri", card_title, card_comp, "skipped", "no apply button found"],
                sheet_name=sheet_name,
                role=role,
                posted_time=card_posted,
                job_url=card_url,
                username=username
            )
            return False

        safe_print(f"  👉 Clicking Apply for: {card_title} @ {card_comp}...")
        clicked, note = click_native_apply(page)
        if note == "daily_quota_exceeded":
            safe_print("\n" + "!" * 70)
            safe_print("🛑 [NAUKRI DAILY LIMIT REACHED]: Naukri daily apply quota (50 jobs) is exhausted for today!")
            safe_print("   Naukri account quota resets at 12:00 AM midnight.")
            safe_print("!" * 70 + "\n")
            log_row(
                [datetime.now(), "naukri", card_title, card_comp, "limit_reached", "Daily quota reached — resets at 12:00 AM"],
                sheet_name=sheet_name,
                role=role,
                posted_time=card_posted,
                job_url=card_url,
                username=username
            )
            try:
                from common.engine_manager import engine_manager
                engine_manager.mark_daily_limit("naukri", reason="Daily quota reached — resets at 12:00 AM", username=username)
            except Exception:
                pass
            raise StopRun("daily quota of jobs exceeded")

        if not clicked:
            safe_print(f"  ⚠️ Skipped: {card_title} @ {card_comp} — apply button click didn't register ({note})")
            log_row(
                [datetime.now(), "naukri", card_title, card_comp, "skipped", "apply button click didn't register"],
                sheet_name=sheet_name,
                role=role,
                posted_time=card_posted,
                job_url=card_url,
                username=username
            )
            return False
        time.sleep(1.2)

        answer_screening_chat(page, profile, f"{card_title} at {card_comp}", human_timeout)
        time.sleep(1.2)

        verify_applied(page)

        if applied_lock:
            with applied_lock:
                already_applied.add((card_title.lower(), card_comp.lower()))
        else:
            already_applied.add((card_title.lower(), card_comp.lower()))

        detection_tag = "⚡ INSTANT RADAR APPLY (HR Posted)" if sheet_name == "Sheet2" else ""
        log_row(
            [datetime.now(), "naukri", card_title, card_comp, "applied", detection_tag],
            sheet_name=sheet_name,
            role=role,
            posted_time=card_posted,
            job_url=card_url,
            username=username
        )

        try:
            from common.engine_manager import engine_manager
            from backend.app.services.browser_manager import browser_manager
            engine_manager.increment_applied("naukri", username=username)
            engine_manager.update_action("naukri", f"Applied: {card_title}")
            browser_manager.notify_application_completed(username or "admin", "naukri")
        except Exception:
            pass

        if sheet_name == "Sheet2":
            safe_print(f"  ⚡ [INSTANT RADAR SUCCESS] Applied to fresh HR posting: {card_title} @ {card_comp} (Role: {role} | Posted: {card_posted}) -> Logged to Sheet2")
        else:
            safe_print(f"  ✅ [APPLIED] {card_title} @ {card_comp} (Role: {role} | Posted: {card_posted}) -> Logged to Sheet1")
        return True

    except SkipJob as e:
        log_row(
            [datetime.now(), "naukri", card_title, card_comp, "skipped", str(e)],
            sheet_name=sheet_name,
            role=role,
            posted_time=card_posted,
            job_url=card_url,
            username=username
        )
        safe_print(f"  ⏭️ Skipped: {card_title} @ {card_comp} — {e}")
        if applied_lock:
            with applied_lock:
                already_applied.add((card_title.lower(), card_comp.lower()))
        else:
            already_applied.add((card_title.lower(), card_comp.lower()))
        return False
    except StopRun:
        raise
    except Exception as e:
        log_row(
            [datetime.now(), "naukri", card_title, card_comp, "skipped", f"unexpected error: {e}"],
            sheet_name=sheet_name,
            role=role,
            posted_time=card_posted,
            job_url=card_url,
            username=username
        )
        safe_print(f"  ⚠️ Skipped (unexpected error): {card_title} @ {card_comp} — {e}")
        return False


def is_posted_within_10_minutes(posted_str: str, datetime_attr: str = "") -> bool:
    """Checks whether a job posting timestamp string is within the last 10 minutes.
    Uses common.time_filter.is_job_within_age_limit to parse relative and ISO formats.
    """
    ok, _ = is_job_within_age_limit(text=posted_str, datetime_attr=datetime_attr)
    return ok


def radar_worker(
    profile: Profile,
    already_applied: set,
    applied_lock,
    stop_event: threading.Event,
    only_fresh_10min: bool = False,
    only_fresh: bool = False,
    fresh_threshold_minutes: int = 10,
    username: str = None
):
    """Parallel Engine 1: Continuously scans fresh HR postings (sortBy=f, jobAge=1) and applies instantly to Sheet2."""
    exp_param = int(profile.total_experience_years)
    force_headless = os.environ.get("HEADLESS", "false").lower() == "true" or os.environ.get("RENDER") is not None
    browser_mode = os.environ.get("BROWSER_MODE", "headless" if force_headless else "minimized").lower()

    from backend.app.services.browser_manager import browser_manager

    page = browser_manager.get_sync_page(username=username or "admin", site="naukri")
    safe_print("[RADAR ENGINE ⚡] Live Radar worker active and scanning for fresh HR postings...")

    if True:
        while not stop_event.is_set():
            for role in profile.target_roles:
                if stop_event.is_set():
                    break
                slug = role.lower().replace(" ", "-")
                url = f"https://www.naukri.com/{slug}-jobs?experience={exp_param}&jobAge=1&sortBy=f"
                try:
                    page.goto(url, timeout=12000)
                    page.wait_for_selector('.srp-jobtuple-wrapper[data-job-id]', timeout=4000)
                except Exception:
                    continue

                stop = page_has_stop_signal(page)
                if stop:
                    if "daily quota" in stop:
                        safe_print("\n🛑 [NAUKRI DAILY LIMIT REACHED]: Daily quota reached for today! Reset at 12:00 AM.")
                        try:
                            from common.engine_manager import engine_manager
                            engine_manager.mark_daily_limit(
                                "naukri",
                                reason="Daily quota reached — resets at 12:00 AM"
                            )
                        except Exception:
                            pass
                    else:
                        safe_print(f"[RADAR] Stop signal detected: {stop}")
                    stop_event.set()
                    break

                cards = enumerate_cards(page)
                try:
                    from common.engine_manager import engine_manager
                    if engine_manager.get_engine_state("naukri").get("daily_limit_exceeded"):
                        safe_print("\n🛑 [NAUKRI] Daily quota reached for today. Halting radar worker.")
                        stop_event.set()
                        break
                except Exception:
                    pass
                for card in cards[:6]:  # Inspect top newest HR postings
                    if stop_event.is_set():
                        break
                    card_title = (card.get("title") or "").strip()
                    card_comp = (card.get("company") or "").strip()

                    with applied_lock:
                        if (card_title.lower(), card_comp.lower()) in already_applied:
                            continue

                    posted_str = card.get("posted") or ""
                    dt_attr = card.get("datetime_attr") or ""
                    # Freshness filter: skip jobs older than dynamic threshold when enabled
                    fresh_enabled = only_fresh_10min
                    fresh_threshold = 10
                    try:
                        from common.engine_manager import engine_manager
                        fresh_enabled, fresh_threshold = engine_manager.get_fresh_settings("naukri")
                    except Exception:
                        pass

                    if fresh_enabled:
                        fresh_ok, fresh_reason = is_job_within_age_limit(
                            text=posted_str,
                            datetime_attr=dt_attr,
                            max_minutes=fresh_threshold
                        )
                        # If posted_str is not empty or generic, skip immediately to save time
                        if not fresh_ok and posted_str and posted_str.lower() not in ("today", ""):
                            safe_print(f"  [RADAR] Skipping ({fresh_reason}): {card_title} | Posted: {posted_str}")
                            log_row(
                                [datetime.now(), "naukri", card_title, card_comp, "skipped", fresh_reason],
                                sheet_name="Sheet2",
                                role=role,
                                posted_time=posted_str,
                                job_url=card.get("href", ""),
                                username=username
                            )
                            with applied_lock:
                                if card.get("jobId"):
                                    already_applied.add(card.get("jobId"))
                                already_applied.add((card_title.lower(), card_comp.lower()))
                            continue
                    safe_print(f"\n⚡ [RADAR ALERT] Fresh HR job found: {card_title} @ {card_comp} (Role: {role} | Posted: {posted_str or 'Just Now'})")
                    try:
                        apply_single_job(
                            page,
                            card,
                            profile,
                            role,
                            already_applied,
                            sheet_name="Sheet2",
                            applied_lock=applied_lock,
                            only_fresh_10min=only_fresh_10min,
                            username=username
                        )
                    except StopRun as e:
                        if "daily quota" in str(e).lower():
                            safe_print("\n🛑 [NAUKRI DAILY LIMIT REACHED]: Daily quota reached for today! Reset at 12:00 AM.")
                            try:
                                from common.engine_manager import engine_manager
                                engine_manager.mark_daily_limit(
                                    "naukri",
                                    reason="Daily quota reached — resets at 12:00 AM",
                                    username=username
                                )
                            except Exception:
                                pass
                        stop_event.set()
                        break
                    time.sleep(2)

            # Rapid cooldown between radar scans (30 seconds)
            for _ in range(30):
                if stop_event.is_set():
                    break
                time.sleep(1)

        try:
            from backend.app.services.browser_manager import browser_manager
            browser_manager.mark_engine_stopped(username or "admin", "naukri")
        except Exception:
            pass


def sweep_worker(
    profile: Profile,
    already_applied: set,
    applied_lock,
    stop_event: threading.Event,
    only_fresh_10min: bool = False,
    only_fresh: bool = False,
    fresh_threshold_minutes: int = 10,
    username: str = None
):
    """Parallel Engine 2: Continuously crawls standard search results (pages 1 to max_pages) and applies to Sheet1."""
    exp_param = int(profile.total_experience_years)
    max_pages = profile.data.get("max_pages_per_role", 15)
    force_headless = os.environ.get("HEADLESS", "false").lower() == "true" or os.environ.get("RENDER") is not None
    browser_mode = os.environ.get("BROWSER_MODE", "headless" if force_headless else "minimized").lower()

    from backend.app.services.browser_manager import browser_manager

    page = browser_manager.get_sync_page(username=username or "admin", site="naukri")
    safe_print("[SWEEP ENGINE 🔄] Standard crawler active and sweeping paginated job lists...")

    if True:
        cycle = 0
        while not stop_event.is_set():
            cycle += 1
            safe_print(f"\n" + "=" * 65)
            safe_print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔄 Standard Sweep Cycle #{cycle} starting in parallel...")
            safe_print(f"=" * 65)

            for role in profile.target_roles:
                if stop_event.is_set():
                    break
                slug = role.lower().replace(" ", "-")
                seen_job_ids = set()

                for page_no in range(1, max_pages + 1):
                    if stop_event.is_set():
                        break
                    fresh_enabled = only_fresh_10min
                    fresh_threshold = 10
                    try:
                        from common.engine_manager import engine_manager
                        fresh_enabled, fresh_threshold = engine_manager.get_fresh_settings("naukri")
                    except Exception:
                        pass

                    if fresh_enabled and fresh_threshold <= 60 and page_no > 1:
                        # Ultra-fresh jobs (< 60 min) typically only exist on page 1
                        break
                    page_suffix = "" if page_no == 1 else f"-{page_no}"
                    sort_param = "&sortBy=f" if fresh_enabled else ""
                    age_filter_val = 1 if (fresh_enabled and fresh_threshold <= 1440) else profile.job_freshness_days
                    url = (
                        f"https://www.naukri.com/{slug}-jobs{page_suffix}"
                        f"?experience={exp_param}"
                        f"&jobAge={age_filter_val}"
                        f"{sort_param}"
                    )
                    try:
                        page.goto(url, timeout=15000)
                        page.wait_for_selector('.srp-jobtuple-wrapper[data-job-id]', timeout=6000)
                    except Exception:
                        pass

                    stop = page_has_stop_signal(page)
                    if stop:
                        if "daily quota" in stop:
                            safe_print("\n🛑 [NAUKRI DAILY LIMIT REACHED]: Daily quota reached for today! Reset at 12:00 AM.")
                            try:
                                from common.engine_manager import engine_manager
                                engine_manager.mark_daily_limit(
                                    "naukri",
                                    reason="Daily quota reached — resets at 12:00 AM"
                                )
                            except Exception:
                                pass
                        else:
                            safe_print(f"[SWEEP] Stop signal detected: {stop}")
                        stop_event.set()
                        break

                    cards = enumerate_cards(page)
                    try:
                        from common.engine_manager import engine_manager
                        if engine_manager.get_engine_state("naukri").get("daily_limit_exceeded"):
                            safe_print("\n🛑 [NAUKRI] Daily quota reached for today. Halting sweep worker.")
                            stop_event.set()
                            break
                    except Exception:
                        pass
                    new_cards = [c for c in cards if c.get("jobId") not in seen_job_ids]
                    if not new_cards:
                        break

                    for card in new_cards:
                        if stop_event.is_set():
                            break
                        seen_job_ids.add(card.get("jobId"))
                        card_title = (card.get("title") or "").strip()
                        card_comp = (card.get("company") or "").strip()

                        with applied_lock:
                            if (card_title.lower(), card_comp.lower()) in already_applied:
                                continue

                        posted_str = card.get("posted") or ""
                        dt_attr = card.get("datetime_attr") or ""
                        fresh_enabled = only_fresh_10min
                        fresh_threshold = 10
                        try:
                            from common.engine_manager import engine_manager
                            fresh_enabled, fresh_threshold = engine_manager.get_fresh_settings("naukri")
                        except Exception:
                            pass

                        if fresh_enabled:
                            fresh_ok, fresh_reason = is_job_within_age_limit(
                                text=posted_str,
                                datetime_attr=dt_attr,
                                max_minutes=fresh_threshold
                            )
                            if not fresh_ok and posted_str and posted_str.lower() not in ("today", ""):
                                safe_print(f"  [SWEEP] Skipping ({fresh_reason}): {card_title} | Posted: {posted_str}")
                                log_row(
                                    [datetime.now(), "naukri", card_title, card_comp, "skipped", fresh_reason],
                                    sheet_name="Sheet1",
                                    role=role,
                                    posted_time=posted_str,
                                    job_url=card.get("href", ""),
                                    username=username
                                )
                                with applied_lock:
                                    if card.get("jobId"):
                                        already_applied.add(card.get("jobId"))
                                    already_applied.add((card_title.lower(), card_comp.lower()))
                                try:
                                    from common.engine_manager import engine_manager
                                    current_pace = engine_manager.get_pacing("naukri")
                                except Exception:
                                    current_pace = profile.pace_seconds_between_actions
                                time.sleep(current_pace)
                                continue

                        try:
                            apply_single_job(
                                page,
                                card,
                                profile,
                                role,
                                already_applied,
                                sheet_name="Sheet1",
                                applied_lock=applied_lock,
                                only_fresh_10min=only_fresh_10min,
                                username=username
                            )
                        except StopRun as e:
                            if "daily quota" in str(e).lower():
                                safe_print("\n🛑 [NAUKRI DAILY LIMIT REACHED]: Daily quota reached for today! Reset at 12:00 AM.")
                                try:
                                    from common.engine_manager import engine_manager
                                    engine_manager.mark_daily_limit(
                                        "naukri",
                                        reason="Daily quota reached — resets at 12:00 AM",
                                        username=username
                                    )
                                except Exception:
                                    pass
                            stop_event.set()
                            break
                        try:
                            from common.engine_manager import engine_manager
                            current_pace = engine_manager.get_pacing("naukri")
                        except Exception:
                            current_pace = profile.pace_seconds_between_actions
                        time.sleep(current_pace)

            # Seamless continuous sweep: immediate transition to next search cycle with configured pace
            try:
                from common.engine_manager import engine_manager
                current_pace = engine_manager.get_pacing("naukri")
            except Exception:
                current_pace = profile.pace_seconds_between_actions
            safe_print(f"\n[Sweep Cycle #{cycle} Complete] Continuously starting next search cycle (pace: {current_pace:.1f}s)...")
            time.sleep(min(current_pace, 2.0))

        try:
            from backend.app.services.browser_manager import browser_manager
            browser_manager.mark_engine_stopped(username or "admin", "naukri")
        except Exception:
            pass


def run(continuous: bool = True):
    profile = Profile.load()
    if not SESSION_FILE.exists():
        raise SystemExit(f"{SESSION_FILE} not found. Run: python login_capture.py naukri")

    already_applied = load_already_applied()
    applied_lock = threading.Lock()
    stop_event = threading.Event()

    safe_print("=" * 65)
    safe_print("      🚀 NAUKRI DUAL-ENGINE PARALLEL AUTONOMOUS BOT")
    safe_print("=" * 65)
    safe_print(f"Candidate: Kunal Kumar ({profile.total_experience_years} Years Experience)")
    safe_print(f"Target Roles: {', '.join(profile.target_roles)}")
    safe_print(f"Google Sheet: {google_sheet.GOOGLE_SHEET_URL}")
    safe_print(f"  - Sheet1: 🔄 Standard Continuous Auto-Apply (Background Crawler)")
    safe_print(f"  - Sheet2: ⚡ Instant Live Radar (Scans fresh HR posts in parallel)")
    safe_print(f"Loaded {len(already_applied)} previously applied jobs from cache/sheet.")
    safe_print("Both engines running in PARALLEL... (Press Ctrl+C anytime to stop)")
    safe_print("=" * 65)

    # Start both engines in parallel threads
    t_radar = threading.Thread(
        target=radar_worker,
        args=(profile, already_applied, applied_lock, stop_event),
        name="RadarWorker"
    )
    t_sweep = threading.Thread(
        target=sweep_worker,
        args=(profile, already_applied, applied_lock, stop_event),
        name="SweepWorker"
    )

    t_radar.daemon = True
    t_sweep.daemon = True

    t_radar.start()
    t_sweep.start()

    try:
        while t_radar.is_alive() or t_sweep.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        safe_print("\n[INFO] Stop signal received. Gracefully shutting down parallel engines...")
        stop_event.set()
        t_radar.join(timeout=5)
        t_sweep.join(timeout=5)
        safe_print("[INFO] Bot stopped cleanly by user.")


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        safe_print("\n[INFO] Bot stopped by user. Clean exit.")


