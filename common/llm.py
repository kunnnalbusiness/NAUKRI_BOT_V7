"""
LLM screening-answer orchestrator with automated multi-key rotation and multi-provider failover.
Hierarchy:
1. Active Gemini Key -> Next available Gemini Key on quota/429
2. Fallback to Active Groq Key -> Next available Groq Key
3. Informative error if all keys across all providers are exhausted/invalid.
"""

from common import gemini
from common import groq_llm
from common import key_rotator
from common.runtime_config import mask_key


def draft_answer(question: str, profile_data: dict, job_context: str = "") -> str:
    # 1. Try Gemini keys (loop through available healthy keys)
    gemini_errors = []
    tried_gemini_ids = set()
    while True:
        key_obj = key_rotator.get_active_key("gemini")
        if not key_obj:
            break
        key_id = key_obj.get("id")
        if key_id in tried_gemini_ids:
            break
        tried_gemini_ids.add(key_id)

        try:
            ans = gemini.draft_answer(question, profile_data, job_context)
            if ans and ans.strip():
                return ans.strip()
            break
        except Exception as e:
            gemini_errors.append(f"Gemini({mask_key(key_obj.get('key'))}): {e}")

    # 2. Try Groq keys (loop through available healthy keys)
    groq_errors = []
    tried_groq_ids = set()
    while True:
        key_obj = key_rotator.get_active_key("groq")
        if not key_obj:
            break
        key_id = key_obj.get("id")
        if key_id in tried_groq_ids:
            break
        tried_groq_ids.add(key_id)

        try:
            ans = groq_llm.draft_answer(question, profile_data, job_context)
            if ans and ans.strip():
                return ans.strip()
            break
        except Exception as e:
            groq_errors.append(f"Groq({mask_key(key_obj.get('key'))}): {e}")

    # If we get here, all configured keys failed
    all_errs = "; ".join(gemini_errors + groq_errors)
    if not all_errs:
        raise RuntimeError(
            "No enabled and active AI API keys configured for Gemini or Groq."
        )
    raise RuntimeError(f"All LLM keys failed: {all_errs}")
