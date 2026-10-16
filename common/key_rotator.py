"""
Multi-key manager and automatic rotation system for Gemini and Groq.
Handles:
- Key rotation on 429 / quota / rate limit errors
- Cooldown timer tracking and auto-recovery
- Masked key management for dashboard
- Live key testing (small cheap API calls)
"""

import time
import uuid
import threading
from typing import Dict, Any, Optional, List

from common.runtime_config import (
    get_config,
    update_config,
    get_raw_keys,
    mask_key,
)

DEFAULT_COOLDOWN_SECONDS = 300  # 5 minutes for quota recovery


class KeyRotator:
    """Manages AI provider API keys with state tracking, automatic rotation, and failover."""

    def __init__(self):
        self._lock = threading.RLock()
        self._keys: List[Dict[str, Any]] = []

    def set_keys(self, keys: List[Dict[str, Any]]):
        """Sets internal keys list (useful for test isolation)."""
        with self._lock:
            self._keys = list(keys)

    def add_key(
        self,
        provider: str,
        key_val: str,
        enabled: bool = True,
        name: Optional[str] = None,
    ) -> str:
        """Adds a new key. Returns key_id."""
        provider = provider.lower().strip()
        if provider not in ("gemini", "groq"):
            raise ValueError("Provider must be 'gemini' or 'groq'")
        clean_key = key_val.strip()
        if not clean_key:
            raise ValueError("API Key cannot be empty")

        key_id = f"{provider}_{uuid.uuid4().hex[:8]}"
        label = (name or f"{provider.capitalize()} Key").strip()

        with self._lock:
            # Also sync in-memory for testing
            new_obj = {
                "id": key_id,
                "provider": provider,
                "name": label,
                "key": clean_key,
                "enabled": bool(enabled),
                "status": "Active",
                "last_error": None,
                "exhausted_until": None,
            }
            self._keys.append(new_obj)

            def mutate(cfg):
                if "api_keys" not in cfg:
                    cfg["api_keys"] = {"gemini": [], "groq": []}
                if provider not in cfg["api_keys"]:
                    cfg["api_keys"][provider] = []

                # Update if exists
                for k in cfg["api_keys"][provider]:
                    if k.get("key") == clean_key:
                        k["name"] = label
                        k["enabled"] = bool(enabled)
                        k["status"] = "Active"
                        return cfg

                cfg["api_keys"][provider].append(new_obj)
                if not cfg.get(f"active_{provider}_key_id"):
                    cfg[f"active_{provider}_key_id"] = key_id
                return cfg

            update_config(mutate)
            return key_id

    def update_key(
        self,
        key_id: str,
        enabled: Optional[bool] = None,
        name: Optional[str] = None,
        new_key: Optional[str] = None,
    ) -> bool:
        """Updates an existing API key's enabled status or secret."""
        with self._lock:
            for k in self._keys:
                if k["id"] == key_id:
                    if enabled is not None:
                        k["enabled"] = bool(enabled)
                    if name is not None:
                        k["name"] = name.strip()
                    if new_key is not None and new_key.strip():
                        k["key"] = new_key.strip()
                        k["status"] = "Active"
                        k["last_error"] = None
                        k["exhausted_until"] = None

            def mutate(cfg):
                for prov in ("gemini", "groq"):
                    keys = cfg.get("api_keys", {}).get(prov, [])
                    for k in keys:
                        if k.get("id") == key_id:
                            if name is not None:
                                k["name"] = name.strip()
                            if enabled is not None:
                                k["enabled"] = bool(enabled)
                            if new_key is not None and new_key.strip():
                                k["key"] = new_key.strip()
                                k["status"] = "Active"
                                k["last_error"] = None
                                k["exhausted_until"] = None
                            return cfg
                return cfg

            update_config(mutate)
            return True

    def remove_key(self, key_id: str) -> bool:
        """Removes an API key from the store."""
        with self._lock:
            self._keys = [k for k in self._keys if k["id"] != key_id]

            def mutate(cfg):
                for prov in ("gemini", "groq"):
                    keys = cfg.get("api_keys", {}).get(prov, [])
                    cfg["api_keys"][prov] = [k for k in keys if k.get("id") != key_id]
                    if cfg.get(f"active_{prov}_key_id") == key_id:
                        rem = cfg["api_keys"][prov]
                        cfg[f"active_{prov}_key_id"] = rem[0]["id"] if rem else None
                return cfg

            update_config(mutate)
            return True

    delete_key = remove_key

    def get_next_key(self, provider: str) -> Optional[Dict[str, Any]]:
        """Returns the next healthy key for the provider, rotating on exhaustion."""
        provider = provider.lower().strip()
        now = time.time()

        with self._lock:
            # If self._keys has keys (e.g. In unit tests), check them first
            prov_keys = [
                k for k in self._keys if k.get("provider", "").lower() == provider
            ]
            if not prov_keys:
                # Read from runtime config
                prov_keys = get_raw_keys(provider)

            if not prov_keys:
                return None

            # Look for active/available key
            for k in prov_keys:
                if not k.get("enabled", True):
                    continue
                st = k.get("status", "Active")
                if st == "Invalid":
                    continue
                ex_until = k.get("exhausted_until")
                if st == "Exhausted" and ex_until:
                    if now < ex_until:
                        continue
                    else:
                        # Cooldown expired! Reset to Active
                        k["status"] = "Active"
                        k["exhausted_until"] = None

                # Found healthy key
                return k

            return None

    get_active_key = get_next_key

    def mark_key_failure(
        self,
        key_id: str,
        error_msg: str,
        is_exhausted: bool = True,
        is_invalid: bool = False,
        cooldown_s: int = DEFAULT_COOLDOWN_SECONDS,
    ):
        """Marks a key as exhausted or invalid."""
        now = time.time()
        with self._lock:
            status_val = "Invalid" if is_invalid else "Exhausted"
            ex_until = None if is_invalid else (now + cooldown_s)

            for k in self._keys:
                if k["id"] == key_id:
                    k["status"] = status_val
                    k["last_error"] = str(error_msg)[:150]
                    k["exhausted_until"] = ex_until

            def mutate(cfg):
                for prov in ("gemini", "groq"):
                    keys = cfg.get("api_keys", {}).get(prov, [])
                    for k in keys:
                        if k.get("id") == key_id:
                            k["status"] = status_val
                            k["last_error"] = str(error_msg)[:150]
                            k["exhausted_until"] = ex_until
                            return cfg
                return cfg

            update_config(mutate)

    def mark_key_exhausted(
        self,
        provider: str,
        key_id: str,
        error_msg: str,
        cooldown_s: int = DEFAULT_COOLDOWN_SECONDS,
    ):
        self.mark_key_failure(
            key_id,
            error_msg,
            is_exhausted=True,
            is_invalid=False,
            cooldown_s=cooldown_s,
        )

    def mark_key_invalid(self, provider: str, key_id: str, error_msg: str):
        self.mark_key_failure(key_id, error_msg, is_exhausted=False, is_invalid=True)

    def mark_key_active(self, provider: str, key_id: str):
        """Marks a key as active after successful call."""
        with self._lock:
            for k in self._keys:
                if k["id"] == key_id:
                    k["status"] = "Active"
                    k["last_error"] = None
                    k["exhausted_until"] = None

            def mutate(cfg):
                for prov in ("gemini", "groq"):
                    keys = cfg.get("api_keys", {}).get(prov, [])
                    for k in keys:
                        if k.get("id") == key_id:
                            k["status"] = "Active"
                            k["last_error"] = None
                            k["exhausted_until"] = None
                            return cfg
                return cfg

            update_config(mutate)

    def get_masked_keys(self) -> List[Dict[str, Any]]:
        """Returns all configured keys with secrets masked (never returning full key)."""
        now = time.time()
        with self._lock:
            res: List[Dict[str, Any]] = []

            # If internal keys populated (tests)
            if self._keys:
                for k in self._keys:
                    ex_until = k.get("exhausted_until")
                    st = k.get("status", "Active")
                    rem = max(0, ex_until - now) if ex_until else 0
                    if st == "Exhausted" and rem == 0:
                        st = "Active"

                    res.append(
                        {
                            "id": k["id"],
                            "provider": k.get("provider", "gemini"),
                            "name": k.get("name", "Key"),
                            "masked_key": mask_key(k.get("key")),
                            "enabled": bool(k.get("enabled", True)),
                            "status": st,
                            "last_error": k.get("last_error"),
                            "cooldown_remaining": rem,
                        }
                    )
                return res

            # Otherwise read from config
            cfg = get_config()
            all_keys = cfg.get("api_keys", {})
            for prov in ("gemini", "groq"):
                for k in all_keys.get(prov, []):
                    ex_until = k.get("exhausted_until")
                    st = k.get("status", "Active")
                    rem = max(0, ex_until - now) if ex_until else 0
                    if st == "Exhausted" and rem == 0:
                        st = "Active"

                    res.append(
                        {
                            "id": k["id"],
                            "provider": prov,
                            "name": k.get("name", f"{prov.title()} Key"),
                            "masked_key": mask_key(k.get("key")),
                            "enabled": bool(k.get("enabled", True)),
                            "status": st,
                            "last_error": k.get("last_error"),
                            "cooldown_remaining": rem,
                        }
                    )
            return res

    def get_status(self) -> Dict[str, Any]:
        """Returns overview status of LLM keys for dashboard."""
        keys = self.get_masked_keys()
        active_gemini = self.get_next_key("gemini")
        active_groq = self.get_next_key("groq")

        curr = None
        if active_gemini:
            curr = f"Gemini ({mask_key(active_gemini.get('key'))})"
        elif active_groq:
            curr = f"Groq ({mask_key(active_groq.get('key'))})"

        return {
            "current_key": curr,
            "keys": keys,
        }

    def test_key(self, key_id: str) -> Dict[str, Any]:
        """Tests validity of a specific API key."""
        target = None
        for k in self._keys:
            if k["id"] == key_id:
                target = k
                break

        if not target:
            cfg = get_config()
            for prov in ("gemini", "groq"):
                for k in cfg.get("api_keys", {}).get(prov, []):
                    if k.get("id") == key_id:
                        target = dict(k)
                        target["provider"] = prov
                        break

        if not target:
            return {"success": False, "message": "Key not found", "status": "Unknown"}

        prov = target.get("provider", "gemini").lower()
        key_val = target.get("key", "").strip()

        if prov == "gemini":
            try:
                from google import genai

                client = genai.Client(api_key=key_val)
                pager = client.models.list(config={"page_size": 1})
                _ = next(iter(pager), None)
                self.mark_key_active("gemini", key_id)
                return {
                    "success": True,
                    "message": "Gemini key verified successfully.",
                    "status": "Active",
                }
            except Exception as e:
                err = str(e)
                if any(h in err.lower() for h in ["401", "403", "api_key_invalid"]):
                    self.mark_key_invalid("gemini", key_id, err)
                    return {
                        "success": False,
                        "message": f"Auth failed: {err[:80]}",
                        "status": "Invalid",
                    }
                elif "429" in err or "quota" in err.lower():
                    self.mark_key_exhausted("gemini", key_id, err)
                    return {
                        "success": False,
                        "message": f"Quota reached: {err[:80]}",
                        "status": "Exhausted",
                    }
                return {
                    "success": False,
                    "message": f"Error: {err[:80]}",
                    "status": "Invalid",
                }

        elif prov == "groq":
            try:
                from groq import Groq

                client = Groq(api_key=key_val)
                _ = client.models.list()
                self.mark_key_active("groq", key_id)
                return {
                    "success": True,
                    "message": "Groq key verified successfully.",
                    "status": "Active",
                }
            except Exception as e:
                err = str(e)
                if any(h in err.lower() for h in ["401", "403", "unauthorized"]):
                    self.mark_key_invalid("groq", key_id, err)
                    return {
                        "success": False,
                        "message": f"Auth failed: {err[:80]}",
                        "status": "Invalid",
                    }
                elif "429" in err or "quota" in err.lower():
                    self.mark_key_exhausted("groq", key_id, err)
                    return {
                        "success": False,
                        "message": f"Quota reached: {err[:80]}",
                        "status": "Exhausted",
                    }
                return {
                    "success": False,
                    "message": f"Error: {err[:80]}",
                    "status": "Invalid",
                }

        return {
            "success": False,
            "message": f"Unknown provider {prov}",
            "status": "Unknown",
        }


# Global singleton instance
key_rotator = KeyRotator()

# Module-level alias functions for backwards compatibility
add_key = key_rotator.add_key
update_key = key_rotator.update_key
delete_key = key_rotator.delete_key
get_active_key = key_rotator.get_active_key
get_next_key = key_rotator.get_next_key
mark_key_active = key_rotator.mark_key_active
mark_key_exhausted = key_rotator.mark_key_exhausted
mark_key_invalid = key_rotator.mark_key_invalid
test_key = key_rotator.test_key
get_masked_keys = key_rotator.get_masked_keys
