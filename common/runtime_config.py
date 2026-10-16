"""
Encrypted runtime configuration store for naukri-job-apply-ai.
Stores persistent runtime settings (engine switches, API keys, Google Sheet settings)
in an encrypted JSON file (Fernet) in DATA_DIR/config/runtime.json.

Priority order:
1. Runtime store (DATA_DIR/config/runtime.json)
2. Environment variables (os.environ)
3. Local .env file

Thread-safe with atomic writes. Secrets never leak in logs, errors, or public APIs.
"""

import os
import json
import base64
import hashlib
import threading
import time
from typing import Any, Dict, List, Optional
from cryptography.fernet import Fernet, InvalidToken

from common.paths import get_runtime_config_path, get_env_path

_lock = threading.RLock()
_cached_config: Optional[Dict[str, Any]] = None
_last_mtime: float = 0.0


def _derive_fernet_key(secret: Optional[str] = None) -> bytes:
    """Derives a deterministic 32-byte URL-safe base64 Fernet key from SECRET_KEY."""
    if not secret:
        # Check env or .env
        secret = os.environ.get("SECRET_KEY")
        if not secret:
            env_file = get_env_path()
            if env_file.exists():
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    if line.strip().startswith("SECRET_KEY="):
                        secret = line.split("=", 1)[1].strip()
                        break
    if not secret:
        # Safe fallback secret for local development
        secret = "naukri-job-apply-ai-default-local-secret-key-2026"

    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def mask_key(val: Optional[str]) -> str:
    """Returns masked secret showing only the last 4 characters, e.g. '...4F8b'."""
    if not val:
        return ""
    clean = str(val).strip()
    if len(clean) <= 4:
        return "****"
    return f"...{clean[-4:]}"


def _read_env_file() -> Dict[str, str]:
    """Reads key-values from .env if present."""
    data = {}
    env_file = get_env_path()
    if env_file.exists():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    data[k.strip()] = v.strip().strip("'\"")
        except Exception:
            pass
    return data


def _get_default_seed() -> Dict[str, Any]:
    """Creates the initial default config seeded from environment variables and .env."""
    env_file_data = _read_env_file()

    def get_var(name: str, default: str = "") -> str:
        return os.environ.get(name) or env_file_data.get(name, default)

    gemini_key = get_var("GEMINI_API_KEY")
    groq_key = get_var("GROQ_API_KEY")
    webhook_url = get_var("GOOGLE_SHEET_WEBHOOK_URL")
    sheet_url = get_var(
        "GOOGLE_SHEET_URL",
        "https://docs.google.com/spreadsheets/d/1-J4aod-jEImTQ1QQDM9seK7oVqYpTxn9-Tzj2V-rMNQ/edit?usp=sharing",
    )

    gemini_keys: List[Dict[str, Any]] = []
    if gemini_key:
        gemini_keys.append(
            {
                "id": "gemini_1",
                "name": "Primary Gemini",
                "key": gemini_key,
                "enabled": True,
                "status": "active",
                "last_error": None,
                "exhausted_until": None,
            }
        )

    groq_keys: List[Dict[str, Any]] = []
    if groq_key:
        groq_keys.append(
            {
                "id": "groq_1",
                "name": "Primary Groq",
                "key": groq_key,
                "enabled": True,
                "status": "active",
                "last_error": None,
                "exhausted_until": None,
            }
        )

    return {
        "engines": {"naukri": {"enabled": False}, "linkedin": {"enabled": False}},
        "api_keys": {"gemini": gemini_keys, "groq": groq_keys},
        "google_sheet": {"webhook_url": webhook_url, "sheet_url": sheet_url},
        "active_gemini_key_id": "gemini_1" if gemini_keys else None,
        "active_groq_key_id": "groq_1" if groq_keys else None,
    }


def _load_raw_config() -> Dict[str, Any]:
    """Loads and decrypts runtime config file, or initializes it on first boot."""
    global _cached_config, _last_mtime
    config_path = get_runtime_config_path()

    if not config_path.exists():
        # First boot: seed from environment variables and save
        initial = _get_default_seed()
        _save_raw_config(initial)
        _cached_config = initial
        return initial

    try:
        mtime = config_path.stat().st_mtime
        if _cached_config is not None and mtime == _last_mtime:
            return _cached_config

        raw_encrypted = config_path.read_bytes()
        fernet = Fernet(_derive_fernet_key())
        decrypted = fernet.decrypt(raw_encrypted)
        data = json.loads(decrypted.decode("utf-8"))
        _cached_config = data
        _last_mtime = mtime
        return data
    except (InvalidToken, Exception):
        # If decryption fails (e.g. key changed), backup broken file and reseed
        try:
            backup_path = config_path.with_suffix(".corrupt.bak")
            config_path.rename(backup_path)
        except Exception:
            pass
        initial = _get_default_seed()
        _save_raw_config(initial)
        _cached_config = initial
        return initial


def _save_raw_config(data: Dict[str, Any]) -> None:
    """Encrypts and atomically writes config data to DATA_DIR/config/runtime.json."""
    global _cached_config, _last_mtime
    config_path = get_runtime_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    fernet = Fernet(_derive_fernet_key())
    payload = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    encrypted = fernet.encrypt(payload)

    # Atomic write pattern: write to tmp file then rename/replace
    tmp_path = config_path.with_suffix(".tmp")
    tmp_path.write_bytes(encrypted)
    os.replace(str(tmp_path), str(config_path))

    _cached_config = data
    _last_mtime = config_path.stat().st_mtime


def get_config() -> Dict[str, Any]:
    """Returns a full copy of the runtime configuration."""
    with _lock:
        return json.loads(json.dumps(_load_raw_config()))


def update_config(mutator) -> Dict[str, Any]:
    """Thread-safe update helper that applies mutator function to the config."""
    with _lock:
        current = _load_raw_config()
        updated = mutator(current) or current
        _save_raw_config(updated)
        return json.loads(json.dumps(updated))


# ---------------------------------------------------------------------------
# Specific High-Level Accessors
# ---------------------------------------------------------------------------


def get_engine_enabled(site: str) -> bool:
    """Returns whether the specified engine (naukri or linkedin) is enabled."""
    with _lock:
        cfg = _load_raw_config()
        return bool(cfg.get("engines", {}).get(site.lower(), {}).get("enabled", False))


def set_engine_enabled(site: str, enabled: bool) -> None:
    """Toggles engine enabled state in persistent config."""
    with _lock:

        def mutate(cfg):
            if "engines" not in cfg:
                cfg["engines"] = {}
            if site.lower() not in cfg["engines"]:
                cfg["engines"][site.lower()] = {}
            cfg["engines"][site.lower()]["enabled"] = bool(enabled)
            return cfg

        update_config(mutate)


def get_google_sheet_settings() -> Dict[str, str]:
    """Returns Google Sheet webhook URL and Sheet URL (runtime > env > .env)."""
    with _lock:
        cfg = _load_raw_config()
        gs = cfg.get("google_sheet", {})
        webhook = gs.get("webhook_url")
        sheet_url = gs.get("sheet_url")

        env_data = _read_env_file()
        if not webhook:
            webhook = os.environ.get("GOOGLE_SHEET_WEBHOOK_URL") or env_data.get(
                "GOOGLE_SHEET_WEBHOOK_URL", ""
            )
        if not sheet_url:
            sheet_url = os.environ.get("GOOGLE_SHEET_URL") or env_data.get(
                "GOOGLE_SHEET_URL", ""
            )

        return {"webhook_url": webhook or "", "sheet_url": sheet_url or ""}


def set_google_sheet_settings(
    webhook_url: Optional[str] = None, sheet_url: Optional[str] = None
) -> None:
    """Updates Google Sheet webhook URL and sheet link in persistent config."""
    with _lock:

        def mutate(cfg):
            if "google_sheet" not in cfg:
                cfg["google_sheet"] = {}
            if webhook_url is not None:
                cfg["google_sheet"]["webhook_url"] = webhook_url.strip()
            if sheet_url is not None:
                cfg["google_sheet"]["sheet_url"] = sheet_url.strip()
            return cfg

        update_config(mutate)


def get_public_keys(provider: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Returns masked keys and status for dashboard API (never exposes full raw keys)."""
    with _lock:
        cfg = _load_raw_config()
        all_keys = cfg.get("api_keys", {})
        out: Dict[str, List[Dict[str, Any]]] = {}

        now = time.time()
        providers = [provider.lower()] if provider else ["gemini", "groq"]

        for prov in providers:
            prov_keys = all_keys.get(prov, [])
            clean_list = []
            for k in prov_keys:
                status = k.get("status", "unknown")
                exhausted_until = k.get("exhausted_until")
                if status == "exhausted" and exhausted_until and now >= exhausted_until:
                    status = "active"

                clean_list.append(
                    {
                        "id": k["id"],
                        "name": k.get("name", "Key"),
                        "key_masked": mask_key(k.get("key")),
                        "enabled": bool(k.get("enabled", True)),
                        "status": status,
                        "last_error": k.get("last_error"),
                        "exhausted_until": exhausted_until,
                        "is_active_key": k["id"] == cfg.get(f"active_{prov}_key_id"),
                    }
                )
            out[prov] = clean_list

        return out


def get_raw_keys(provider: str) -> List[Dict[str, Any]]:
    """Internal use only: returns unmasked keys for LLM execution."""
    with _lock:
        cfg = _load_raw_config()
        return list(cfg.get("api_keys", {}).get(provider.lower(), []))


def get_config_value(key: str, default: Any = None) -> Any:
    """
    Priority resolution:
    1. Runtime encrypted store (DATA_DIR/config/runtime.json)
    2. Environment variables (os.environ)
    3. .env file
    4. default
    """
    with _lock:
        cfg = _load_raw_config()
        if key in cfg:
            return cfg[key]
        if key == "GOOGLE_SHEET_URL":
            val = cfg.get("google_sheet", {}).get("sheet_url")
            if val:
                return val
        elif key == "GOOGLE_SHEET_WEBHOOK_URL":
            val = cfg.get("google_sheet", {}).get("webhook_url")
            if val:
                return val
        elif key == "NAUKRI_ENABLED":
            return str(
                cfg.get("engines", {}).get("naukri", {}).get("enabled", False)
            ).lower()
        elif key == "LINKEDIN_ENABLED":
            return str(
                cfg.get("engines", {}).get("linkedin", {}).get("enabled", False)
            ).lower()

        # Check os.environ
        if key in os.environ:
            return os.environ[key]

        # Check .env file
        env_dict = _read_env_file()
        if key in env_dict:
            return env_dict[key]

        return default


def set_config_value(key: str, value: Any) -> None:
    """Sets a configuration value in the encrypted runtime store atomically."""
    with _lock:

        def mutate(cfg):
            cfg[key] = value
            if key == "GOOGLE_SHEET_URL":
                if "google_sheet" not in cfg:
                    cfg["google_sheet"] = {}
                cfg["google_sheet"]["sheet_url"] = str(value)
            elif key == "GOOGLE_SHEET_WEBHOOK_URL":
                if "google_sheet" not in cfg:
                    cfg["google_sheet"] = {}
                cfg["google_sheet"]["webhook_url"] = str(value)
            elif key == "NAUKRI_ENABLED":
                if "engines" not in cfg:
                    cfg["engines"] = {}
                if "naukri" not in cfg["engines"]:
                    cfg["engines"]["naukri"] = {}
                cfg["engines"]["naukri"]["enabled"] = str(value).lower() == "true"
            elif key == "LINKEDIN_ENABLED":
                if "engines" not in cfg:
                    cfg["engines"] = {}
                if "linkedin" not in cfg["engines"]:
                    cfg["engines"]["linkedin"] = {}
                cfg["engines"]["linkedin"]["enabled"] = str(value).lower() == "true"
            return cfg

        update_config(mutate)


def delete_config_value(key: str) -> None:
    """Deletes a key from the encrypted runtime store."""
    with _lock:

        def mutate(cfg):
            cfg.pop(key, None)
            return cfg

        update_config(mutate)
