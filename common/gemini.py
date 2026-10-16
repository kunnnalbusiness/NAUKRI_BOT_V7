"""
Generates free-text screening answers using Google's Gemini API via google-genai SDK.
Integrates with key_rotator for live multi-key rotation, quota detection, and automatic recovery.
"""

import os
from google import genai
from google.genai import types

from common import key_rotator

MODEL = "gemini-3.1-flash-lite"  # Active free-tier Flash model

_SYSTEM_INSTRUCTIONS = """\
You are an intelligent job application assistant drafting a concise, professional answer to a job screening question on behalf of the applicant described below.

Rules:
1. Ground your answers in the applicant's experience, background, and skills.
2. If asked about experience with any technology, tool, methodology, or skill: Answer affirmatively and highlight relevant Python, PySpark, Data Engineering, SQL, automation, or analytics experience.
3. If asked about whether the applicant is an ex-employee or asks for previous employee ID (e.g. "if not mention NA"): Answer "NA".
4. If asked about notice period, relocation, shifts, or joining date: Answer affirmatively and align with the applicant's profile (30 days notice, willing to relocate).
5. Keep answers short, direct, and professional (1-2 sentences).
6. Write in first person ("I have...", "Yes, I...").
7. NEVER refuse to answer and NEVER return [NEEDS_HUMAN_INPUT]. Always give the best answer that allows the application to proceed.
"""


def _build_prompt(question: str, profile_data: dict, job_context: str = "") -> str:
    parts = []
    if job_context:
        parts.append(f"JOB CONTEXT:\n{job_context}\n")
    parts.append("APPLICANT PROFILE:")
    for k in (
        "current_title_functional",
        "current_title_official",
        "total_experience_years",
        "current_employer",
        "notice_period_days",
        "current_ctc_lpa",
        "expected_ctc_lpa",
        "current_city",
        "relocate_cities",
        "highest_qualification",
        "skills_primary",
        "work_history_narrative",
    ):
        v = profile_data.get(k)
        if v:
            parts.append(f"  {k}: {v}")
    parts.append(f"\nSCREENING QUESTION:\n{question}\n")
    parts.append(
        "Provide ONLY the direct answer text. Do not include greetings, explanations, or quotes."
    )
    return "\n".join(parts)


def draft_answer(question: str, profile_data: dict, job_context: str = "") -> str:
    key_obj = key_rotator.get_active_key("gemini")
    key_val = key_obj.get("key") if key_obj else os.environ.get("GEMINI_API_KEY")
    key_id = key_obj.get("id") if key_obj else "env_key"

    if not key_val:
        raise RuntimeError("No Gemini API key configured.")

    try:
        client = genai.Client(api_key=key_val)
        prompt = _build_prompt(question, profile_data, job_context)
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_INSTRUCTIONS,
                max_output_tokens=150,
                temperature=0.2,
            ),
        )
        text = (response.text or "").strip()
        if key_obj and key_id:
            key_rotator.mark_key_active("gemini", key_id)
        return text

    except Exception as e:
        err_str = str(e)
        err_lower = err_str.lower()
        if key_obj and key_id:
            if any(h in err_lower for h in ["429", "quota", "resource_exhausted"]):
                key_rotator.mark_key_exhausted(
                    "gemini", key_id, err_str, cooldown_s=300
                )
            elif any(h in err_lower for h in ["401", "403", "api_key_invalid"]):
                key_rotator.mark_key_invalid("gemini", key_id, err_str)
        raise
