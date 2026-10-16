"""
LinkedIn Easy Apply. Requires session_linkedin.json from login_capture.py.

LinkedIn's automation detection is meaningfully tighter than Naukri's — keep
pace_seconds_between_actions generous, and expect this to need more manual
babysitting than the Naukri script. Stop instantly on any CAPTCHA, login
prompt, or "you've reached the Easy Apply limit" message.

Usage:
    python linkedin_apply.py
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
import threading
import re
import os
import csv
import time
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("linkedin_apply")

from playwright.sync_api import TimeoutError as PWTimeout

from common.profile import Profile
from common import llm
from common import google_sheet
from common.paths import get_session_path
from common.time_filter import is_job_within_age_limit
from common.access_detector import check_page_access_denied

SESSION_FILE = get_session_path("linkedin")

STOP_PHRASES = [
    "easy apply limit", "unusual activity", "verify it's you",
    "captcha", "security verification", "we've restricted",
]


def log_row(row: list, username: str = None):
    google_sheet.record_application(
        timestamp=row[0],
        source=row[1],
        title=row[2],
        company=row[3],
        status=row[4],
        reason=str(row[5]) if len(row) > 5 else "",
        username=username
    )


def check_limit_reached(page) -> str | None:
    """
    Robustly checks if LinkedIn's daily Easy Apply limit has been reached.
    Scans all open dialogs, alertdialogs, modals, headings, and page body.
    """
    try:
        res = page.evaluate("""() => {
            const limitPhrases = [
                "easy apply limit",
                "reached today's easy apply limit",
                "reached today’s easy apply limit",
                "we limit easy apply submissions",
                "we limit easy apply",
                "continue applying tomorrow",
                "daily easy apply limit",
                "daily limit reached"
            ];

            // 1. Scan all open dialogs & modals
            const dialogs = Array.from(document.querySelectorAll('dialog, [role="alertdialog"], [role="dialog"], .artdeco-modal, [data-test-modal]'));
            for (const d of dialogs) {
                if (d.tagName === 'DIALOG' && !d.open) continue;
                const style = window.getComputedStyle(d);
                if (style.display === 'none' || style.visibility === 'hidden') continue;

                const txt = (d.innerText || '').toLowerCase();
                for (const p of limitPhrases) {
                    if (txt.includes(p)) return `Dialog: ${p}`;
                }
                const hasGotIt = Array.from(d.querySelectorAll('button')).some(b => (b.innerText || '').toLowerCase().includes('got it'));
                if (hasGotIt && (txt.includes('limit') || txt.includes('tomorrow') || txt.includes('reached'))) {
                    return "Dialog: Easy Apply daily limit reached";
                }
            }

            // 2. Scan headings
            const headings = Array.from(document.querySelectorAll('h1, h2, h3, .jobs-easy-apply-modal__header'));
            for (const h of headings) {
                const txt = (h.innerText || '').toLowerCase();
                if ((txt.includes('limit') && txt.includes('reached')) || txt.includes('easy apply limit')) {
                    return `Heading: ${txt}`;
                }
            }

            // 3. Scan body text with strict phrases only
            const bodyLimitPhrases = [
                "easy apply limit",
                "reached today's easy apply limit",
                "reached today’s easy apply limit",
                "we limit easy apply submissions",
                "we limit easy apply",
                "continue applying tomorrow",
                "daily easy apply limit"
            ];
            const body = (document.body ? document.body.innerText : '').toLowerCase();
            for (const p of bodyLimitPhrases) {
                if (body.includes(p)) return `Page: ${p}`;
            }

            return null;
        }""")
        return res
    except Exception:
        return None


def page_has_stop_signal(page) -> str | None:
    blocked, block_msg = check_page_access_denied(page, site="linkedin")
    if blocked:
        return f"access denied / blocked ({block_msg})"

    lim = check_limit_reached(page)
    if lim:
        return f"easy apply limit ({lim})"
    try:
        text = page.inner_text("body").lower()
        for phrase in STOP_PHRASES:
            if phrase in text:
                return phrase
    except Exception:
        pass
    if "/checkpoint/" in page.url or "/login" in page.url:
        return "session expired / checkpoint challenge"
    return None


def check_job_applied_state(page, card=None) -> tuple[bool, str]:
    """
    Checks if a job is already applied, either from card text/badge or details pane.
    Returns (is_applied, reason_message).
    """
    # 1. Check card element text for genuine applied badge
    if card:
        try:
            import re
            card_text = (card.inner_text() or "").lower()
            lines = [l.strip() for l in card_text.split("\n") if l.strip()]
            for line in lines:
                # Genuine applied badge matches "applied", "applied today", "applied 2d ago", etc.
                # Must not falsely match "applied to 1 other job", "applied filters", or "applied skills"
                if re.match(r"^applied(\s+(today|yesterday|\d+\s*[dwmyh](?:r|rs|ays|eeks|onths|ears)?\s*ago|\d+[dwmyh]))?$", line):
                    return True, f"Already applied previously ({line})"
        except Exception:
            pass

    # 2. Check details pane top card for explicit Applied button or status badge
    try:
        details_applied = page.evaluate(r"""() => {
            const topCard = document.querySelector('.job-details-jobs-unified-top-card, .jobs-details__main-content, main');
            if (!topCard) return { applied: false };
            const els = Array.from(topCard.querySelectorAll('button, .artdeco-inline-feedback, span[class*="status"]'));
            for (const el of els) {
                const txt = (el.innerText || '').trim().toLowerCase();
                const aria = (el.getAttribute('aria-label') || '').trim().toLowerCase();
                const rect = el.getBoundingClientRect();
                if (rect.width > 20 && rect.height > 12) {
                    if (txt === 'applied' || aria === 'applied' || /^applied\s+(\d+\s*[dwmyh]|today|yesterday)/i.test(txt)) {
                        return { applied: true, text: txt || aria };
                    }
                }
            }
            return { applied: false };
        }""")
        if details_applied and details_applied.get("applied"):
            return True, f"Already applied previously ({details_applied.get('text', 'Applied')})"
    except Exception:
        pass

    return False, ""


def has_external_apply_only(page) -> bool:
    """Checks if the details pane only offers an external application link (x >= 580, y >= 180, y <= 750)."""
    try:
        return page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('button, a[role="button"], a'));
            // Details pane action area strictly: x >= 580, y between 180 and 750
            const detailsBtns = btns.filter(b => {
                const r = b.getBoundingClientRect();
                return r.x >= 580 && r.y >= 180 && r.y <= 750 && r.width > 20 && r.height > 15 && !b.disabled;
            });

            // If there's an Easy Apply button in the details pane, it is NOT external only
            const hasEasy = detailsBtns.some(b => {
                const txt = (b.innerText || '').toLowerCase();
                const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                return (txt === 'easy apply' || aria.includes('easy apply')) && !aria.includes('filter') && !aria.includes('dismiss');
            });
            if (hasEasy) return false;

            // Check if there is an external Apply button or link in details pane
            return detailsBtns.some(b => {
                const txt = (b.innerText || '').trim().toLowerCase();
                const aria = (b.getAttribute('aria-label') || '').trim().toLowerCase();
                const href = (b.getAttribute('href') || '').toLowerCase();
                const isApply = txt === 'apply' || txt.includes('apply on') || aria.includes('apply on') || aria.includes('apply to') || href.includes('apply');
                const notEasy = !txt.includes('easy apply') && !aria.includes('easy apply');
                return isApply && notEasy;
            });
        }""")
    except Exception:
        return False


def click_easy_apply_button(page) -> bool:
    """
    Finds and clicks the primary 'Easy Apply' button or link strictly in the LinkedIn job details pane.
    Restricts search to x >= 580 (right of search results card list) and y >= 180 (below top search filter bar)
    to prevent false clicks on top filter bar pills or job card dismiss buttons.
    """
    for _ in range(8):
        # 1. Evaluate DOM to find precise target coordinates and element
        target = None
        try:
            target = page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button, a[role="button"], a.jobs-apply-button'));
                for (const b of btns) {
                    const r = b.getBoundingClientRect();
                    const txt = (b.innerText || '').trim().toLowerCase();
                    const aria = (b.getAttribute('aria-label') || '').trim().toLowerCase();
                    const isEasy = (txt === 'easy apply' || aria.includes('easy apply')) && !aria.includes('filter') && !aria.includes('dismiss');
                    // Details pane constraint: x >= 580, y between 180 and 750
                    if (isEasy && r.x >= 580 && r.y >= 180 && r.y <= 750 && r.width >= 25 && r.height >= 15 && !b.disabled) {
                        return {
                            x: Math.round(r.x + r.width / 2),
                            y: Math.round(r.y + r.height / 2),
                            text: txt,
                            aria: aria
                        };
                    }
                }
                return null;
            }""")
        except Exception:
            pass

        if target:
            try:
                # Click center of the real Easy Apply button in details pane
                page.mouse.click(target["x"], target["y"])
                return True
            except Exception:
                pass

        # 2. Scoped Playwright locator fallback
        try:
            locs = page.locator("button, a, [role='button']").filter(
                has_not=page.locator("visible=false")
            )
            count = locs.count()
            for i in range(count):
                btn = locs.nth(i)
                box = btn.bounding_box()
                if not box or box["x"] < 580 or box["y"] < 180 or box["y"] > 750 or box["width"] < 25 or box["height"] < 15:
                    continue
                txt = (btn.inner_text() or "").strip().lower()
                aria = (btn.get_attribute("aria-label") or "").lower()
                if ("easy apply" in txt or "easy apply" in aria) and "filter" not in aria and "dismiss" not in aria and "dismiss" not in txt:
                    try:
                        btn.scroll_into_view_if_needed(timeout=2000)
                        btn.click(timeout=3000)
                        return True
                    except Exception:
                        btn.evaluate("el => el.click()")
                        return True
        except Exception:
            pass

        time.sleep(0.5)

    return False


def dismiss_modal(page):
    """Safely dismisses and discards any open Easy Apply modal dialog or limit notification."""
    try:
        # Step 1: Click dismiss/close button on modal
        for _ in range(3):
            clicked = page.evaluate("""() => {
                const modal = document.querySelector('dialog[open], [role="dialog"], [role="alertdialog"], .artdeco-modal, .jobs-easy-apply-modal');
                const root = modal || document;
                const btns = Array.from(root.querySelectorAll('button'));
                const closeBtn = btns.find(b => {
                    const rect = b.getBoundingClientRect();
                    const txt = (b.innerText || '').toLowerCase();
                    const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                    return (aria.includes('dismiss') || aria.includes('close') || txt.includes('got it') || txt.includes('cancel'))
                        && !aria.includes('job') && rect.x > 350;
                });
                if (closeBtn) {
                    closeBtn.click();
                    return true;
                }
                return false;
            }""")
            if clicked:
                break
            time.sleep(0.3)

        time.sleep(0.8)

        # Step 2: Handle confirmation dialog ("Discard" or "Save")
        for _ in range(3):
            discarded = page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button, [role="button"]'));
                const discard = btns.find(b => {
                    const txt = (b.innerText || '').trim().toLowerCase();
                    const aria = (b.getAttribute('aria-label') || '').trim().toLowerCase();
                    const dataTest = (b.getAttribute('data-test-dialog-primary-btn') || '').toLowerCase();
                    return txt.includes('discard') || aria.includes('discard') || dataTest.includes('discard');
                });
                if (discard) {
                    discard.click();
                    return true;
                }
                return false;
            }""")
            if discarded:
                break
            time.sleep(0.3)
    except Exception:
        pass


def describe_modal(page) -> dict:
    """Extracts all form fields, options, radio groups, buttons, and error messages from the open Easy Apply modal."""
    return page.evaluate("""
        () => {
            // 1. Locate modal container (must be strictly open and visible)
            let modal = document.querySelector('dialog[open], [role="dialog"], [role="alertdialog"], .jobs-easy-apply-modal, .artdeco-modal, [data-test-modal]');
            if (modal) {
                if (modal.tagName === 'DIALOG' && !modal.open) modal = null;
                if (modal) {
                    const r = modal.getBoundingClientRect();
                    const style = window.getComputedStyle(modal);
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0' || r.width < 250 || r.height < 80) {
                        modal = null;
                    }
                }
            }
            if (!modal) {
                const candidates = Array.from(document.querySelectorAll('dialog, [role="dialog"], [role="alertdialog"], [class*="modal"]'));
                modal = candidates.find(c => {
                    if (c.tagName === 'DIALOG' && !c.open) return false;
                    const r = c.getBoundingClientRect();
                    const style = window.getComputedStyle(c);
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                    return r.width >= 300 && r.height >= 80 && r.width <= 1100 && r.y >= 0;
                });
            }
            if (!modal) return {error: 'no dialog found'};

            const heading = modal.querySelector('h1, h2, h3, header, .jobs-easy-apply-modal__header')?.innerText?.trim() || '';
            const modalFullText = (modal.innerText || '').toLowerCase();
            const headingLower = heading.toLowerCase();

            // Check if this modal is LinkedIn's Easy Apply Daily Limit dialog
            if (
                headingLower.includes('easy apply limit') ||
                (headingLower.includes('reached') && headingLower.includes('limit')) ||
                modalFullText.includes("reached today's easy apply limit") ||
                modalFullText.includes("reached today’s easy apply limit") ||
                modalFullText.includes("we limit easy apply") ||
                modalFullText.includes("continue applying tomorrow") ||
                (modalFullText.includes('limit') && (modalFullText.includes('got it') || modalFullText.includes('tomorrow')))
            ) {
                return {
                    is_limit_reached: true,
                    heading: heading || "Daily Easy Apply limit reached",
                    buttons: ['Got it'],
                    fields: [],
                    radioGroups: {},
                    errors: []
                };
            }

            const fields = [];
            const buttons = [];
            const errors = [];

            // Helper to get closest label or legend text
            function findLabel(el) {
                if (el.getAttribute('aria-label')) return el.getAttribute('aria-label').trim();
                if (el.id) {
                    const lbl = modal.querySelector(`label[for="${el.id}"]`);
                    if (lbl) return lbl.innerText.trim();
                }
                const parentContainer = el.closest('.fb-dash-form-element, .jobs-easy-apply-form-element, .artdeco-form-element, .fb-form-element, div');
                if (parentContainer) {
                    const lbl = parentContainer.querySelector('label, legend, .fb-form-element-label, span.t-14, p, span');
                    if (lbl) return lbl.innerText.trim();
                }
                const parentLbl = el.closest('label');
                if (parentLbl) return parentLbl.innerText.trim();
                return el.placeholder || '';
            }

            // Text, Number, Tel, Email, and Textarea fields
            modal.querySelectorAll('input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]):not([type="file"]), textarea').forEach(el => {
                fields.push({
                    tag: el.tagName,
                    type: el.type || 'text',
                    id: el.id || '',
                    label: findLabel(el),
                    value: el.value || '',
                    required: el.required || el.getAttribute('aria-required') === 'true'
                });
            });

            // Radio Groups
            const radioGroups = {};
            modal.querySelectorAll('input[type="radio"]').forEach(el => {
                const name = el.name || 'unnamed_radio';
                if (!radioGroups[name]) {
                    const container = el.closest('fieldset, .fb-form-element, div') || el.parentElement;
                    const question = container ? (container.querySelector('legend, label, span.t-14, p, span')?.innerText?.trim() || '') : '';
                    radioGroups[name] = { question, options: [] };
                }
                const optLabel = el.closest('label')?.innerText?.trim() || el.value || '';
                radioGroups[name].options.push({
                    id: el.id,
                    value: el.value,
                    label: optLabel,
                    checked: el.checked
                });
            });

            // Select Dropdowns
            modal.querySelectorAll('select').forEach(el => {
                const options = Array.from(el.options).map(o => ({ value: o.value, text: o.text.trim() }));
                fields.push({
                    tag: 'SELECT',
                    type: 'select',
                    id: el.id || '',
                    label: findLabel(el),
                    value: el.value || '',
                    options
                });
            });

            // Action Buttons
            modal.querySelectorAll('button').forEach(b => {
                const t = (b.innerText || b.getAttribute('aria-label') || '').trim();
                if (t && b.offsetParent !== null) buttons.push(t);
            });

            // Error alerts
            modal.querySelectorAll('.artdeco-inline-feedback--error, [data-test-form-element-error-messages], [class*="error"], [role="alert"]').forEach(e => {
                const errTxt = e.innerText.trim();
                if (errTxt && !errors.includes(errTxt)) errors.push(errTxt);
            });

            return { heading, fields, radioGroups, buttons, errors };
        }
    """)


def fill_text_field(page, field_id: str, text: str):
    """Sets input value directly and dispatches events so React/LinkedIn registers input."""
    page.evaluate(
        """([id, text]) => {
            const el = document.getElementById(id);
            if (!el) return false;
            el.focus();
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
                        || Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
            if (setter) {
                setter.call(el, text);
            } else {
                el.value = text;
            }
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            el.dispatchEvent(new Event('blur', {bubbles: true}));
            return true;
        }""",
        [field_id, text],
    )


def fill_form_step(page, profile: Profile, job_context: str) -> list[str]:
    """Inspects all fields on current step and fills inputs, radio groups, and dropdowns."""
    answers = profile.answer_library()
    state = describe_modal(page)
    if state.get("error"):
        time.sleep(1.0)
        state = describe_modal(page)

    filled_actions = []

    # 1. Fill Text & Textarea fields
    for field in state.get("fields", []):
        if field.get("tag") == "SELECT":
            continue
        label = (field.get("label") or "").lower()
        val = (field.get("value") or "").strip()
        field_id = field.get("id")

        if val and not label:
            continue
        if val and any(k in label for k in ["phone", "email", "first name", "last name"]):
            continue

        matched = None
        for key, v in answers.items():
            if key.replace("_", " ") in label or label in key.replace("_", " "):
                matched = v
                break

        # Common profile attributes matching
        if matched is None:
            if "phone" in label or "mobile" in label:
                matched = profile.data.get("phone", "")
            elif "email" in label:
                matched = profile.data.get("email", "")
            elif "experience" in label or "years" in label:
                matched = str(profile.data.get("experience_years", 3))
            elif "notice" in label:
                matched = "Immediate"
            elif "current ctc" in label or "current salary" in label:
                matched = str(profile.data.get("current_ctc", "600000"))
            elif "expected ctc" in label or "expected salary" in label:
                matched = str(profile.data.get("expected_ctc", "800000"))

        # Clean numeric values for inputs that expect digits/numbers
        f_type = (field.get("type") or "text").lower()
        if matched is not None:
            m_str = str(matched).strip()
            if any(k in label for k in ["in days", "notice period in days", "days of notice"]):
                digits = "".join(c for c in m_str if c.isdigit())
                matched = digits if digits else "30"
            elif any(k in label for k in ["in lpa", "mention 18", "if its 18lpa"]):
                digits = "".join(c for c in m_str if c.isdigit() or c == ".")
                matched = digits if digits else "4.5"
            elif any(k in label for k in ["in inr", "in rupees", "rupees"]):
                if "lpa" in m_str.lower() or ("." in m_str and float("".join(c for c in m_str if c.isdigit() or c == ".") or 0) < 100):
                    try:
                        lpa_val = float("".join(c for c in m_str if c.isdigit() or c == "."))
                        matched = str(int(lpa_val * 100000))
                    except Exception:
                        matched = "450000" if "current" in label else "650000"
                else:
                    digits = "".join(c for c in m_str if c.isdigit())
                    matched = digits if digits else ("450000" if "current" in label else "650000")
            elif f_type == "number":
                digits = "".join(c for c in m_str if c.isdigit() or c == ".")
                matched = digits if digits else "3"

        if matched is not None and field_id:
            fill_text_field(page, field_id, str(matched))
            filled_actions.append(f"Filled {label}: {matched}")
        elif not val and field_id:
            # LLM fallback
            try:
                draft = llm.draft_answer(label, profile.data, job_context)
                if not draft.startswith("[NEEDS_HUMAN_INPUT"):
                    if any(k in label for k in ["in days", "days"]):
                        d_clean = "".join(c for c in draft if c.isdigit())
                        draft = d_clean if d_clean else "30"
                    elif any(k in label for k in ["in inr", "in rupees"]):
                        if "lpa" in draft.lower() or ("." in draft and float("".join(c for c in draft if c.isdigit() or c == ".") or 0) < 100):
                            try:
                                lpa_val = float("".join(c for c in draft if c.isdigit() or c == "."))
                                draft = str(int(lpa_val * 100000))
                            except Exception:
                                draft = "450000" if "current" in label else "650000"
                    elif f_type == "number":
                        d_clean = "".join(c for c in draft if c.isdigit() or c == ".")
                        if d_clean:
                            draft = d_clean
                    fill_text_field(page, field_id, draft)
                    filled_actions.append(f"LLM draft for {label}: {draft[:30]}")
            except Exception as e:
                logger.debug(f"LLM draft skip on {label}: {e}")
                # Safe smart fallback to avoid form blockage
                if any(k in label for k in ["experience", "years"]):
                    val_fb = str(profile.data.get("experience_years", 3))
                elif any(k in label for k in ["days", "notice"]):
                    val_fb = "30"
                elif any(k in label for k in ["in inr", "in rupees"]):
                    val_fb = "450000" if "current" in label else "650000"
                elif any(k in label for k in ["in lpa", "mention 18"]):
                    val_fb = "4.5" if "current" in label else "6.5"
                elif any(k in label for k in ["salary", "ctc"]):
                    val_fb = str(profile.data.get("expected_ctc", "800000"))
                else:
                    val_fb = "Yes"
                fill_text_field(page, field_id, val_fb)
                filled_actions.append(f"Fallback for {label}: {val_fb}")

    # 2. Fill Select Dropdowns
    for field in state.get("fields", []):
        if field.get("tag") == "SELECT" and field.get("id"):
            sel_id = field["id"]
            lbl = (field.get("label") or "").lower()
            options = field.get("options", [])
            # Try to match Yes or first valid non-empty option
            page.evaluate("""([id, label]) => {
                const sel = document.getElementById(id);
                if (!sel || sel.value) return;
                let targetIdx = -1;
                for (let i = 0; i < sel.options.length; i++) {
                    const txt = sel.options[i].text.toLowerCase();
                    if (/yes|authorized|immediate|fluent|full/i.test(txt)) {
                        targetIdx = i;
                        break;
                    }
                }
                if (targetIdx === -1 && sel.options.length > 1) {
                    targetIdx = 1;
                }
                if (targetIdx !== -1) {
                    sel.selectedIndex = targetIdx;
                    sel.dispatchEvent(new Event('change', {bubbles: true}));
                }
            }""", [sel_id, lbl])

    # 3. Answer Radio Button Questions
    radio_groups = state.get("radioGroups", {})
    for group_name, group_data in radio_groups.items():
        question = (group_data.get("question") or "").lower()
        options = group_data.get("options", [])
        has_checked = any(opt.get("checked") for opt in options)
        if has_checked:
            continue

        # Determine best answer based on common employment questions
        prefer_yes = True
        if "sponsorship" in question or "require sponsorship" in question or "visa" in question:
            prefer_yes = False  # "Will you now or in future require sponsorship? -> No"

        chosen_id = None
        for opt in options:
            opt_lbl = opt.get("label", "").lower()
            if prefer_yes and "yes" in opt_lbl:
                chosen_id = opt.get("id")
                break
            elif not prefer_yes and "no" in opt_lbl:
                chosen_id = opt.get("id")
                break

        if not chosen_id and options:
            chosen_id = options[0].get("id")

        if chosen_id:
            page.evaluate("""(id) => {
                const el = document.getElementById(id);
                if (el) {
                    el.click();
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }
            }""", chosen_id)
            filled_actions.append(f"Radio {question[:30]}: selected")

    # 4. Uncheck 'Follow company' checkbox if present
    page.evaluate("""() => {
        const followBox = document.querySelector('input[type="checkbox"]#follow-company-checkbox, input[type="checkbox"][id*="follow"]');
        if (followBox && followBox.checked) {
            followBox.click();
        }
    }""")

    # 5. Handle Resume Upload input if step requests a resume
    try:
        file_inputs = page.query_selector_all('input[type="file"]')
        if file_inputs:
            resume_path = profile.get_resolved_resume_path()
            if resume_path and resume_path.exists():
                for fi in file_inputs:
                    try:
                        fi.set_input_files(str(resume_path))
                        filled_actions.append(f"Attached resume: {resume_path.name}")
                    except Exception:
                        pass
    except Exception:
        pass

    return filled_actions


def click_modal_button(page, action: str) -> bool:
    """Clicks matching action button (Next, Review, Submit application, Done, Dismiss) in modal."""
    act_lower = action.lower()

    # 1. DOM evaluate scoped to open modal/dialog first
    clicked = page.evaluate("""(action) => {
        const actLower = action.toLowerCase();
        const modal = document.querySelector('dialog[open], dialog, [role="dialog"], [data-test-modal], .jobs-easy-apply-modal, .artdeco-modal');
        const root = modal || document;
        const btns = Array.from(root.querySelectorAll('button')).filter(b => {
            const rect = b.getBoundingClientRect();
            return (rect.x > 300 || modal) && rect.width > 20 && rect.height > 15 && !b.disabled;
        });
        for (const b of btns) {
            const txt = (b.innerText || '').trim().toLowerCase();
            const aria = (b.getAttribute('aria-label') || '').trim().toLowerCase();
            if (actLower === 'submit' && (txt.includes('submit') || aria.includes('submit'))) {
                b.scrollIntoView(); b.click(); return true;
            }
            if (actLower === 'review' && (txt.includes('review') || aria.includes('review'))) {
                b.scrollIntoView(); b.click(); return true;
            }
            if (actLower === 'next' && (txt === 'next' || txt === 'continue' || aria.includes('next'))) {
                b.scrollIntoView(); b.click(); return true;
            }
            if (actLower === 'done' && (txt.includes('done') || ((aria.includes('dismiss') || aria.includes('close')) && !aria.includes('job')))) {
                b.scrollIntoView(); b.click(); return true;
            }
        }
        return false;
    }""", action)

    if clicked:
        return True

    # 2. Native Playwright fallback
    try:
        for b in page.query_selector_all("button"):
            box = b.bounding_box()
            if not box or box["x"] < 300 or box["width"] < 20 or not b.is_enabled():
                continue
            txt = (b.inner_text() or "").strip().lower()
            aria = (b.get_attribute("aria-label") or "").lower()

            matched = False
            if act_lower == "submit":
                if "submit" in txt or "submit" in aria:
                    matched = True
            elif act_lower == "review":
                if "review" in txt or "review" in aria:
                    matched = True
            elif act_lower == "next":
                if txt in ["next", "continue"] or "continue to next step" in aria:
                    matched = True
            elif act_lower == "done":
                if "done" in txt or (("dismiss" in txt or "dismiss" in aria) and "job" not in aria):
                    matched = True

            if matched:
                try:
                    b.scroll_into_view_if_needed(timeout=2000)
                    b.evaluate("el => el.click()")
                except Exception:
                    b.click(force=True, timeout=3000)
                return True
    except Exception:
        pass

    return False


def run_one_application(page, profile: Profile, job_title: str, company: str, card=None) -> tuple[bool, str]:
    """Runs a complete multi-step LinkedIn Easy Apply submission on the active job page."""
    job_context = f"{job_title} at {company}"

    # Step 0: Check if card element itself already shows applied (pre-filter)
    if card:
        is_applied, applied_reason = check_job_applied_state(page, card)
        if is_applied:
            return False, applied_reason

    # Step 1: Detect and click initial Easy Apply button in details pane
    print(f"[{job_title}] Checking for Easy Apply button in details pane...")
    if not click_easy_apply_button(page):
        # Check if daily limit modal is already open
        lim = check_limit_reached(page)
        if lim:
            dismiss_modal(page)
            try:
                from common.engine_manager import engine_manager
                engine_manager.mark_daily_limit("linkedin", reason="Daily Easy Apply limit reached — resets at midnight")
            except Exception:
                pass
            return False, f"Daily Easy Apply limit reached ({lim})"
        # Determine why it was not clicked
        if has_external_apply_only(page):
            return False, "External application only (not Easy Apply)"
        is_app, r_app = check_job_applied_state(page, card)
        if is_app:
            return False, r_app
        return False, "No Easy Apply button found in details pane"

    # Check if LinkedIn daily limit popup was triggered upon clicking Easy Apply
    time.sleep(1.2)
    limit_sig = check_limit_reached(page)
    if limit_sig:
        # Dismiss limit notification dialog cleanly (click "Got it" or close)
        try:
            page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const b = btns.find(x => {
                    const t = (x.innerText || '').toLowerCase();
                    const a = (x.getAttribute('aria-label') || '').toLowerCase();
                    return t.includes('got it') || a.includes('dismiss') || a.includes('close');
                });
                if (b) b.click();
            }""")
        except Exception:
            pass
        try:
            from common.engine_manager import engine_manager
            engine_manager.mark_daily_limit(
                "linkedin",
                reason="Daily Easy Apply limit reached — resets at midnight"
            )
        except Exception:
            pass
        return False, f"Daily Easy Apply limit reached ({limit_sig})"

    # Wait up to 5s for the modal dialog to appear
    modal_opened = False
    for _ in range(10):
        time.sleep(0.5)
        st = describe_modal(page)
        if st.get("is_limit_reached"):
            dismiss_modal(page)
            try:
                from common.engine_manager import engine_manager
                engine_manager.mark_daily_limit("linkedin", reason="Daily Easy Apply limit reached — resets at midnight")
            except Exception:
                pass
            return False, f"Daily Easy Apply limit reached ({st.get('heading', 'Limit reached')})"
        if not st.get("error"):
            modal_opened = True
            break
        limit_sig = check_limit_reached(page)
        if limit_sig:
            dismiss_modal(page)
            try:
                from common.engine_manager import engine_manager
                engine_manager.mark_daily_limit("linkedin", reason="Daily Easy Apply limit reached — resets at midnight")
            except Exception:
                pass
            return False, f"Daily Easy Apply limit reached ({limit_sig})"

    if not modal_opened:
        if has_external_apply_only(page):
            return False, "External application only (not Easy Apply)"
        return False, "Easy Apply modal failed to open within 5s"

    print(f"[{job_title}] Easy Apply modal opened successfully.")

    # Step 2: Navigate multi-step modal form
    for step_num in range(1, 12):  # Cap at 11 steps
        limit_sig = check_limit_reached(page)
        if limit_sig:
            dismiss_modal(page)
            try:
                from common.engine_manager import engine_manager
                engine_manager.mark_daily_limit("linkedin", reason="Daily Easy Apply limit reached — resets at midnight")
            except Exception:
                pass
            return False, f"Daily Easy Apply limit reached ({limit_sig})"

        state = describe_modal(page)
        if state.get("is_limit_reached"):
            dismiss_modal(page)
            try:
                from common.engine_manager import engine_manager
                engine_manager.mark_daily_limit("linkedin", reason="Daily Easy Apply limit reached — resets at midnight")
            except Exception:
                pass
            return False, f"Daily Easy Apply limit reached ({state.get('heading', 'Limit reached')})"

        stop = page_has_stop_signal(page)
        if stop:
            dismiss_modal(page)
            raise RuntimeError(f"Stop signal during application: {stop}")

        if not state.get("buttons") and not state.get("error"):
            time.sleep(1.0)
            state = describe_modal(page)

        if state.get("error"):
            # Modal closed after submit
            print(f"[{job_title}] Modal closed — submission confirmed!")
            return True, "applied"

        buttons = [b.lower() for b in state.get("buttons", [])]
        heading = state.get("heading", "")
        print(f"[{job_title}] Step {step_num} (Header: '{heading}') - Filling form fields...")
        filled_actions = fill_form_step(page, profile, job_context)
        if filled_actions:
            print(f"[{job_title}] Step {step_num} filled: {', '.join(filled_actions[:3])}")
        time.sleep(0.8)

        # Check for Submit application button
        if any("submit application" in b or b == "submit" for b in buttons):
            print(f"[{job_title}] Reached Submit application step (Step {step_num}). Submitting...")
            clicked_sub = click_modal_button(page, "submit")
            if clicked_sub:
                time.sleep(2.0)
                click_modal_button(page, "done")
                time.sleep(0.5)
                dismiss_modal(page)
                return True, "applied"
            else:
                dismiss_modal(page)
                return False, "Failed to click Submit button"

        # Check for Review step
        elif any("review" in b for b in buttons):
            print(f"[{job_title}] Moving through Review step (Step {step_num})...")
            click_modal_button(page, "review")
            time.sleep(1.5)
            post_state = describe_modal(page)
            if any("review" in b.lower() for b in post_state.get("buttons", [])) and post_state.get("heading") == heading:
                print(f"⚠️ [{job_title}] Review blocked on step {step_num}. Retrying fill...")
                fill_form_step(page, profile, job_context)
                time.sleep(0.5)
                click_modal_button(page, "review")
                time.sleep(1.2)
                if any("review" in b.lower() for b in describe_modal(page).get("buttons", [])):
                    dismiss_modal(page)
                    return False, f"Form validation blocked Review on Step {step_num}"

        # Check for Next step
        elif any("next" in b or "continue" in b for b in buttons):
            print(f"[{job_title}] Proceeding to Next step (Step {step_num})...")
            click_modal_button(page, "next")
            time.sleep(1.2)

            # Check if validation errors blocked progression
            post_state = describe_modal(page)
            errors = post_state.get("errors", [])
            if errors:
                err_summary = "; ".join(errors[:2])
                print(f"⚠️ [{job_title}] Validation error on Step {step_num}: {err_summary}")
                # Try one more fill cycle
                fill_form_step(page, profile, job_context)
                time.sleep(0.5)
                click_modal_button(page, "next")
                time.sleep(1.0)
                final_errs = describe_modal(page).get("errors", [])
                if final_errs:
                    dismiss_modal(page)
                    return False, f"Form validation blocked on Step {step_num}: {'; '.join(final_errs[:2])}"

        # Check if modal is a notification / limit dialog with Got it
        elif any("got it" in b for b in buttons) and any(w in (heading + " " + str(state)).lower() for w in ["limit", "tomorrow", "reached", "effort"]):
            dismiss_modal(page)
            try:
                from common.engine_manager import engine_manager
                engine_manager.mark_daily_limit("linkedin", reason="Daily Easy Apply limit reached — resets at midnight")
            except Exception:
                pass
            return False, f"Daily Easy Apply limit reached ({heading or 'Got it dialog'})"

        else:
            dismiss_modal(page)
            return False, f"Unrecognized modal state on Step {step_num} (buttons: {', '.join(buttons[:5])})"

    dismiss_modal(page)
    return False, "Exceeded step cap (11 steps) without reaching submit"


def is_linkedin_posted_within_10_minutes(text: str, datetime_attr: str = "") -> bool:
    """Verifies that a LinkedIn card satisfies the fresh rule using common.time_filter."""
    ok, _ = is_job_within_age_limit(text=text, datetime_attr=datetime_attr)
    return ok


def run(headless: bool = None, stop_event: threading.Event = None, continuous: bool = False, username: str = None, only_fresh_10min: bool = False, only_fresh: bool = False, fresh_threshold_minutes: int = 10):
    profile = Profile.load_for_user(username)
    session_file = get_session_path("linkedin", username=username)
    if not session_file.exists():
        raise SystemExit(f"{session_file} not found. Run: python login_capture.py linkedin")

    # Load custom delay per user (min safe limit 2s)
    user_delay = 5
    if username:
        try:
            from common.db import get_user_settings
            u_settings = get_user_settings(username)
            user_delay = u_settings.get("delay_seconds", 5)
        except Exception:
            pass
    elif hasattr(profile, "data") and "delay_seconds" in profile.data:
        user_delay = profile.data.get("delay_seconds", 5)

    pace_seconds = max(2, int(user_delay))
    print(f"[Engine Config] Active user: '{username or 'admin'}', Delay between applications: {pace_seconds}s (min safe limit: 2s)")

    if headless is None:
        headless = os.environ.get("HEADLESS", "false").lower() == "true" or os.environ.get("RENDER") is not None

    launch_args = ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"] if headless else []
    # Enable remote debugging port so web dashboard Live View can connect to active bot browser
    launch_args.extend(["--remote-debugging-port=9333"])

    applied = 0
    already_applied = google_sheet.load_applied_jobs(username=username)
    from backend.app.services.browser_manager import browser_manager

    page = browser_manager.get_sync_page(username=username or "admin", site="linkedin")

    if True:
        limit_hit = False
        try:
            from common.engine_manager import engine_manager
            if engine_manager.get_engine_state("linkedin").get("daily_limit_exceeded"):
                print("🛑 LinkedIn daily limit is already marked as reached for today. Halting.", flush=True)
                return
        except Exception:
            pass

        while True:
            if limit_hit or (stop_event and stop_event.is_set()):
                break

            for role in profile.target_roles:
                if limit_hit or (stop_event and stop_event.is_set()) or applied >= profile.stop_after_n_applications:
                    break
                search_url = (
                    "https://www.linkedin.com/jobs/search/?keywords="
                    + role.replace(" ", "%20")
                    + "&f_AL=true"  # Easy Apply filter
                    + "&sortBy=DD"  # Sort by most recent
                )
                fresh_enabled = bool(only_fresh or only_fresh_10min)
                fresh_threshold = fresh_threshold_minutes or 10
                try:
                    from common.engine_manager import engine_manager
                    fresh_enabled, fresh_threshold = engine_manager.get_fresh_settings("linkedin")
                except Exception:
                    pass

                if fresh_enabled:
                    seconds = max(60, fresh_threshold * 60)
                    search_url += f"&f_TPR=r{seconds}"
                print(f"\n--- Searching LinkedIn: {role} ---", flush=True)
                try:
                    from common.engine_manager import engine_manager
                    engine_manager.update_action("linkedin", f"Scanning: {role}")
                except Exception:
                    pass

                try:
                    page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(3.5)
                except Exception as e:
                    print(f"Navigation error: {e}", flush=True)
                    continue

                stop = page_has_stop_signal(page)
                if stop:
                    print(f"STOPPING: {stop}", flush=True)
                    is_lim = "limit" in stop.lower() or "easy apply limit" in stop.lower()
                    log_row([datetime.now(), "linkedin", "-", "-", "limit_reached" if is_lim else "stopped", stop], username=username)
                    if is_lim:
                        try:
                            from common.engine_manager import engine_manager
                            engine_manager.mark_daily_limit(
                                "linkedin",
                                reason="Daily Easy Apply limit reached — resets at midnight"
                            )
                        except Exception:
                            pass
                    if stop_event:
                        stop_event.set()
                    limit_hit = True
                    try:
                        from backend.app.services.browser_manager import browser_manager
                        browser_manager.mark_engine_stopped(username or "admin", "linkedin")
                    except Exception:
                        pass
                    return

                # Discover modern SDUI card components
                card_elements = page.query_selector_all('div[role="button"][componentkey*="job-card"]')
                if not card_elements:
                    card_elements = page.query_selector_all('div[componentkey*="job-card"], button[aria-label*="Dismiss"][aria-label*="job"], .jobs-search-results-list li, .scaffold-layout__list li')

                total_cards = len(card_elements)
                print(f"Discovered {total_cards} job cards for '{role}'", flush=True)
                seen_job_ids = set()

                for idx in range(total_cards):
                    if limit_hit or (stop_event and stop_event.is_set()) or applied >= profile.stop_after_n_applications:
                        break

                    try:
                        from common.engine_manager import engine_manager
                        st = engine_manager.get_engine_state("linkedin")
                        if st.get("daily_limit_exceeded") or st.get("session_applied_count", 0) >= 50 or applied >= 50:
                            print("\n🛑 [LINKEDIN] Daily application limit reached (50 jobs). Halting cleanly.", flush=True)
                            engine_manager.mark_daily_limit("linkedin", reason="Daily Easy Apply limit reached (50 jobs) — resets at midnight")
                            if stop_event:
                                stop_event.set()
                            limit_hit = True
                            break
                    except Exception:
                        pass

                    # Re-query cards to guarantee fresh DOM handles (avoids Element is not attached errors)
                    fresh_cards = page.query_selector_all('div[role="button"][componentkey*="job-card"]')
                    if not fresh_cards:
                        fresh_cards = page.query_selector_all('div[componentkey*="job-card"], button[aria-label*="Dismiss"][aria-label*="job"], .jobs-search-results-list li, .scaffold-layout__list li')
                    if idx >= len(fresh_cards):
                        break
                    card = fresh_cards[idx]

                    try:
                        # Deduplicate by job id if present
                        job_id = card.get_attribute("data-job-id") or card.get_attribute("data-entity-urn") or ""
                        if not job_id:
                            link = card.query_selector("a[href*='/jobs/view/']")
                            if link:
                                href = link.get_attribute("href") or ""
                                m = re.search(r'/jobs/view/(\d+)', href)
                                if m:
                                    job_id = m.group(1)

                        if job_id and job_id in seen_job_ids:
                            continue
                        if job_id:
                            seen_job_ids.add(job_id)

                        # Extract title and company from card text
                        lines = [l.strip() for l in (card.inner_text() or "").split("\n") if l.strip()]
                        title = lines[0].replace("(Verified job)", "").strip() if lines else f"Job #{idx+1}"
                        company = lines[1] if len(lines) > 1 else ""

                        if (title.lower(), company.lower()) in already_applied:
                            continue

                        # Extract precise posted timestamp from card
                        time_text, time_dt = "", ""
                        time_el = card.query_selector("time")
                        if time_el:
                            time_text = (time_el.inner_text() or "").strip()
                            time_dt = time_el.get_attribute("datetime") or ""

                        if not time_text:
                            # In modern LinkedIn SDUI, timestamps are rendered in leaf span tags (e.g. "Posted 1 month ago", "5m ago")
                            try:
                                time_text = card.evaluate(r"""el => {
                                    const spans = Array.from(el.querySelectorAll('*')).filter(e => e.children.length === 0);
                                    for (const s of spans) {
                                        const txt = (s.innerText || '').trim();
                                        if (/^(?:posted\s+)?(?:\d+\s*(?:m|min|minute|h|hr|hour|d|day|w|wk|week|mo|month|y|year)s?(?:\s*ago)?|just now|today)/i.test(txt) && txt.length < 40 && !txt.toLowerCase().includes('inr') && !txt.toLowerCase().includes('lpa')) {
                                            return txt;
                                        }
                                    }
                                    for (const s of spans) {
                                        const txt = (s.innerText || '').trim();
                                        if (/ago|just now|today/i.test(txt) && txt.length < 40 && !txt.toLowerCase().includes('inr') && !txt.toLowerCase().includes('lpa')) {
                                            return txt;
                                        }
                                    }
                                    return '';
                                }""") or ""
                            except Exception:
                                time_text = ""

                        fresh_enabled = bool(only_fresh or only_fresh_10min)
                        fresh_threshold = fresh_threshold_minutes or 10
                        try:
                            from common.engine_manager import engine_manager
                            fresh_enabled, fresh_threshold = engine_manager.get_fresh_settings("linkedin")
                        except Exception:
                            pass

                        if fresh_enabled:
                            fresh_ok, fresh_reason = is_job_within_age_limit(
                                text=time_text,
                                datetime_attr=time_dt,
                                max_minutes=fresh_threshold
                            )
                            if not fresh_ok:
                                print(f"  [LinkedIn Fresh Filter] Skipping ({fresh_reason}): {title} @ {company} (Posted: '{time_text}')", flush=True)
                                log_row([datetime.now(), "linkedin", title, company, "skipped", fresh_reason], username=username)
                                try:
                                    from common.engine_manager import engine_manager
                                    current_pace = engine_manager.get_pacing("linkedin")
                                except Exception:
                                    current_pace = pace_seconds
                                time.sleep(current_pace)
                                continue

                        try:
                            from common.engine_manager import engine_manager
                            engine_manager.update_action("linkedin", f"Reviewing: {title} @ {company}")
                        except Exception:
                            pass

                        # Click card element directly to load details pane
                        try:
                            card.scroll_into_view_if_needed(timeout=2500)
                            card.evaluate("el => el.click()")
                        except Exception:
                            card.click(force=True, timeout=3000)
                        time.sleep(3.0)  # Wait for details pane skeleton to resolve

                        # Extract refined company name and double-check freshness from details pane if enabled
                        if fresh_enabled:
                            try:
                                detail_posted = page.evaluate(r"""() => {
                                    const el = document.querySelector('.job-details-jobs-unified-top-card__primary-description');
                                    if (!el) return '';
                                    const txt = el.innerText || '';
                                    const match = txt.match(/(?:posted\s+)?(?:\d+\s*(?:m|min|minute|h|hr|hour|d|day|w|wk|week|mo|month|y|year)s?(?:\s*ago)?|just now|today)/i);
                                    return match ? match[0] : '';
                                }""") or ""
                                if detail_posted:
                                    fresh_ok_detail, fresh_reason_detail = is_job_within_age_limit(
                                        text=detail_posted,
                                        max_minutes=fresh_threshold
                                    )
                                    if not fresh_ok_detail:
                                        print(f"  [LinkedIn Fresh Filter - Details] Skipping ({fresh_reason_detail}): {title} @ {company} (Details: '{detail_posted}')", flush=True)
                                        log_row([datetime.now(), "linkedin", title, company, "skipped", fresh_reason_detail], username=username)
                                        try:
                                            from common.engine_manager import engine_manager
                                            current_pace = engine_manager.get_pacing("linkedin")
                                        except Exception:
                                            current_pace = pace_seconds
                                        time.sleep(current_pace)
                                        continue
                            except Exception:
                                pass

                        if not company:
                            try:
                                company = page.evaluate("""() => {
                                    const sub = document.querySelector('.job-details-jobs-unified-top-card__primary-description, [class*="company"]');
                                    return sub ? sub.innerText.split('·')[0].trim() : '';
                                }""")
                            except Exception:
                                pass

                        print(f"\n[{idx+1}/{len(card_elements)}] Evaluating: {title} @ {company or 'Company'}", flush=True)
                        success, reason = run_one_application(page, profile, title, company or "LinkedIn Employer", card=card)
                        if success:
                            applied += 1
                            already_applied.add((title.lower(), company.lower()))
                            log_row([datetime.now(), "linkedin", title, company, "applied", ""], username=username)
                            try:
                                from common.engine_manager import engine_manager
                                from backend.app.services.browser_manager import browser_manager
                                engine_manager.increment_applied("linkedin", username=username)
                                engine_manager.update_action("linkedin", f"Applied: {title}")
                                browser_manager.notify_application_completed(username or "admin", "linkedin")
                            except Exception:
                                pass
                            print(f"✓ Applied: {title} @ {company} ({applied} total)", flush=True)

                            if applied >= profile.stop_after_n_applications:
                                print(f"\n🎉 [GOAL REACHED]: Target of {profile.stop_after_n_applications} applications completed for today! Stopping cleanly.", flush=True)
                                try:
                                    from common.engine_manager import engine_manager
                                    engine_manager._update_heartbeat(
                                        "linkedin",
                                        status="Completed",
                                        reason=f"Goal reached: {applied} applications completed today"
                                    )
                                    engine_manager.update_action("linkedin", f"Goal reached: {applied} applications completed")
                                except Exception:
                                    pass
                                if stop_event:
                                    stop_event.set()
                                limit_hit = True
                                break
                        else:
                            reason_lower = (reason or "").lower()
                            is_daily_limit = any(k in reason_lower for k in [
                                "daily easy apply limit",
                                "easy apply limit",
                                "daily limit reached",
                                "daily quota",
                                "limit reached",
                                "limit hit",
                                "limit exceeded",
                                "we limit easy apply"
                            ])

                            if is_daily_limit:
                                print(f"\n🛑 [LINKEDIN DAILY LIMIT REACHED]: {reason}. Halting application engine immediately.", flush=True)
                                log_row([datetime.now(), "linkedin", title, company, "limit_reached", reason], username=username)
                                try:
                                    from common.engine_manager import engine_manager
                                    engine_manager.mark_daily_limit(
                                        "linkedin",
                                        reason="Daily Easy Apply limit reached — resets at midnight"
                                    )
                                except Exception:
                                    pass
                                if stop_event:
                                    stop_event.set()
                                limit_hit = True
                                break
                            else:
                                log_row([datetime.now(), "linkedin", title, company, "skipped", reason], username=username)
                                try:
                                    from common.engine_manager import engine_manager
                                    engine_manager.update_action("linkedin", f"Skipped: {title}")
                                except Exception:
                                    pass
                                print(f"✗ Skipped {title}: {reason}", flush=True)
                    except RuntimeError as e:
                        err_msg = str(e)
                        if "limit" in err_msg.lower() or any(p in err_msg.lower() for p in STOP_PHRASES):
                            print(f"\n🛑 [LINKEDIN STOPPING]: {err_msg}", flush=True)
                            is_lim = "limit" in err_msg.lower() or "easy apply limit" in err_msg.lower()
                            log_row([datetime.now(), "linkedin", title if 'title' in locals() else "-",
                                      company if 'company' in locals() else "-", "limit_reached" if is_lim else "stopped", err_msg], username=username)
                            try:
                                from common.engine_manager import engine_manager
                                if is_lim:
                                    engine_manager.mark_daily_limit("linkedin", reason="Daily Easy Apply limit reached — resets at midnight")
                                else:
                                    engine_manager._update_heartbeat("linkedin", status="Stopped", reason=err_msg[:60])
                            except Exception:
                                pass
                            if stop_event:
                                stop_event.set()
                            limit_hit = True
                            try:
                                from backend.app.services.browser_manager import browser_manager
                                browser_manager.mark_engine_stopped(username or "admin", "linkedin")
                            except Exception:
                                pass
                            return
                        else:
                            print(f"⚠️ Application error: {err_msg}", flush=True)
                            log_row([datetime.now(), "linkedin", title if 'title' in locals() else "-",
                                      company if 'company' in locals() else "-", "skipped", err_msg], username=username)
                            dismiss_modal(page)
                    except Exception as e:
                        print(f"⚠️ Unexpected error on card {idx+1}: {e}", flush=True)
                        dismiss_modal(page)

                    try:
                        from common.engine_manager import engine_manager
                        current_pace = engine_manager.get_pacing("linkedin")
                    except Exception:
                        current_pace = pace_seconds
                    time.sleep(current_pace)

                if limit_hit:
                    break

            goal_reached = applied >= profile.stop_after_n_applications
            if goal_reached:
                print(f"\n🎉 [GOAL REACHED]: Target of {profile.stop_after_n_applications} applications completed for today! Stopping cleanly.", flush=True)
                try:
                    from common.engine_manager import engine_manager
                    engine_manager._update_heartbeat(
                        "linkedin",
                        status="Completed",
                        reason=f"Goal reached: {applied} applications submitted today"
                    )
                    engine_manager.update_action("linkedin", f"Goal reached: {applied} applications submitted")
                except Exception:
                    pass
                if stop_event:
                    stop_event.set()
                break

            if limit_hit or not continuous or (stop_event and stop_event.is_set()):
                break
            # Continuous cycle progression without dead pauses
            try:
                from common.engine_manager import engine_manager
                current_pace = engine_manager.get_pacing("linkedin")
            except Exception:
                current_pace = pace_seconds
            time.sleep(min(current_pace, 2.0))

        try:
            from backend.app.services.browser_manager import browser_manager
            browser_manager.mark_engine_stopped(username or "admin", "linkedin")
        except Exception:
            pass

    print(f"\nDone. {applied} applications submitted this run.")


if __name__ == "__main__":
    run()

