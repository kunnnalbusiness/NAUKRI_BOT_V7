"""
Autonomous screening answer provider.
Answers automatically using AI and profile context instead of halting for user input.
"""

import re


def ask_user(prompt: str, timeout_seconds: int = 0) -> str:
    """Answers automatically without ever pausing the run."""
    lower = prompt.lower()
    print("  [AI Auto-Answer]: Screening question automatically answered.")

    # If it's an options question:
    if "options:" in lower or "choice" in lower:
        # Check if 0 is Yes
        if "0: yes" in lower or "0:yes" in lower:
            return "0"
        # Find any number option that has yes
        yes_match = re.search(r"(\d+):\s*yes", lower)
        if yes_match:
            return yes_match.group(1)
        # Default to first option
        first_opt = re.search(r"(\d+):", lower)
        if first_opt:
            return first_opt.group(1)
        return "0"

    # If question asks for NA if not applicable (e.g. ex-employee, previous ID):
    if any(
        k in lower
        for k in ["if not", "if no", "na", "employee id", "employee no", "ex-employee"]
    ):
        return "NA"

    # If asking about relocation, notice, shifts, availability:
    if any(
        k in lower
        for k in ["shift", "relocate", "relocation", "willing", "comfortable"]
    ):
        return "Yes, I am comfortable with this requirement."

    if any(k in lower for k in ["notice period", "notice", "days"]):
        return "30 days"

    if any(k in lower for k in ["gap", "career gap"]):
        return "No"

    # Try AI via common.llm
    try:
        from common import llm
        from common.profile import Profile

        profile = Profile.load()
        pdata = profile.data
        ans = llm.draft_answer(prompt, pdata).strip()
        if ans and not ans.startswith("[NEEDS_HUMAN_INPUT"):
            return ans
    except Exception:
        pass

    # Positive safe fallback
    if any(k in lower for k in ["do you", "are you", "have you", "can you", "yes/no"]):
        return "Yes"

    return "Yes, I have relevant experience."
