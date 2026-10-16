"""
MongoDB Connection Manager, Index Initializer, and Persistent Store.
Provides connection pooling, Atlas network access guidance, and automatic graceful
fallback to local persistent disk storage when MongoDB is unconfigured or unreachable.
"""

import json
import time
import logging
import threading
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
import pymongo
from pymongo.errors import ServerSelectionTimeoutError, ConfigurationError

from backend.app.core.config import settings
from backend.app.core.security import hash_password, encrypt_text, decrypt_text

logger = logging.getLogger("db.mongo")

_DB_CLIENT: Optional[pymongo.MongoClient] = None
_DB_INSTANCE: Optional[Any] = None
_MONGO_CONNECTED: bool = False
_LOCK = threading.RLock()


def get_local_store_path() -> Path:
    p = settings.DATA_DIR / "users_store.json"
    return p


def _read_local_store() -> Dict[str, Any]:
    path = get_local_store_path()
    if not path.exists():
        return {"users": {}, "profiles": {}, "sessions": {}, "activity": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Error reading local store: {e}")
        return {"users": {}, "profiles": {}, "sessions": {}, "activity": []}


def _write_local_store(data: Dict[str, Any]):
    path = get_local_store_path()
    try:
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        logger.error(f"Error saving local store: {e}")


def get_db():
    """Initializes and returns the MongoDB database or None if using local storage."""
    global _DB_CLIENT, _DB_INSTANCE, _MONGO_CONNECTED

    with _LOCK:
        if _MONGO_CONNECTED and _DB_INSTANCE is not None:
            return _DB_INSTANCE

        mongo_uri = settings.MONGODB_URI
        if mongo_uri:
            try:
                client = pymongo.MongoClient(
                    mongo_uri,
                    serverSelectionTimeoutMS=4000,
                    connectTimeoutMS=4000,
                    maxPoolSize=20,
                    minPoolSize=2,
                    retryWrites=True,
                )
                # Test connectivity
                client.server_info()
                _DB_CLIENT = client
                _DB_INSTANCE = client[settings.DB_NAME]
                _MONGO_CONNECTED = True
                logger.info(
                    f"Successfully connected to MongoDB Atlas (Database: {settings.DB_NAME})"
                )
                _ensure_indexes(_DB_INSTANCE)
                return _DB_INSTANCE
            except (ServerSelectionTimeoutError, ConfigurationError) as e:
                logger.error(
                    "=========================================================================\n"
                    "MONGODB CONNECTION NOTICE:\n"
                    f"Could not connect to MongoDB URI. Error: {e}\n"
                    "If using MongoDB Atlas on Render, make sure to add IP '0.0.0.0/0' to\n"
                    "MongoDB Atlas -> Network Access -> IP Access List.\n"
                    "========================================================================="
                )
                if settings.ENV == "production":
                    raise RuntimeError(
                        f"CRITICAL: Failed to connect to MongoDB Atlas in production environment ({e}). "
                        "Local JSON fallback is strictly disabled in production. "
                        "Verify MONGODB_URI and IP Access List (0.0.0.0/0) in Atlas."
                    )
                logger.warning(
                    "Falling back to local persistent disk storage (/data/users_store.json) for development/local mode."
                )
                _MONGO_CONNECTED = False
                _DB_INSTANCE = None
            except Exception as e:
                if settings.ENV == "production":
                    raise RuntimeError(
                        f"CRITICAL: MongoDB error in production mode: {e}"
                    )
                logger.warning(
                    f"MongoDB connection failed: {e}. Falling back to local persistent store."
                )
                _MONGO_CONNECTED = False
                _DB_INSTANCE = None
        else:
            if settings.ENV == "production":
                raise RuntimeError(
                    "CRITICAL: MONGODB_URI is required in production mode. Local JSON fallback disabled."
                )

        return None


# ---------------------------------------------------------------------------
# GridFS Resume File Storage (Persistent across restarts)
# ---------------------------------------------------------------------------


def save_resume_gridfs(username: str, filename: str, content: bytes) -> Optional[str]:
    """Saves PDF resume bytes into MongoDB GridFS (resilient to ephemeral disk wipes)."""
    db = get_db()
    if db is None:
        return None
    try:
        import gridfs

        fs = gridfs.GridFS(db, collection="resumes_fs")
        for old in fs.find({"username": username}):
            fs.delete(old._id)
        file_id = fs.put(
            content, filename=filename, username=username, uploaded_at=datetime.utcnow()
        )
        logger.info(
            f"Saved resume for user '{username}' into MongoDB GridFS (ID: {file_id})"
        )
        return str(file_id)
    except Exception as e:
        logger.warning(f"Failed to store resume in GridFS: {e}")
        return None


def get_resume_gridfs(username: str) -> Optional[tuple]:
    """Retrieves PDF resume bytes and filename from MongoDB GridFS."""
    db = get_db()
    if db is None:
        return None
    try:
        import gridfs

        fs = gridfs.GridFS(db, collection="resumes_fs")
        doc = fs.find_one({"username": username}, sort=[("uploaded_at", -1)])
        if doc:
            return doc.filename, doc.read()
        return None
    except Exception as e:
        logger.warning(f"Failed to read resume from GridFS: {e}")
        return None


def _ensure_indexes(db):
    """Creates database indexes for fast queries and uniqueness constraints."""
    try:
        db.users.create_index("username", unique=True)
        db.user_profiles.create_index("username", unique=True)
        db.sessions.create_index([("username", 1), ("site", 1)], unique=True)
        db.activity.create_index([("username", 1), ("timestamp", -1)])
        logger.info("MongoDB collection indexes verified.")
    except Exception as e:
        logger.warning(f"Index creation warning: {e}")


# ---------------------------------------------------------------------------
# User Data Access
# ---------------------------------------------------------------------------


def get_user(username: str) -> Optional[Dict[str, Any]]:
    """Retrieves a user document by username."""
    u_clean = username.strip().lower()
    db = get_db()
    if db is not None:
        try:
            doc = db.users.find_one({"username": u_clean})
            if doc:
                doc["_id"] = str(doc["_id"])
                return doc
        except Exception as e:
            logger.warning(f"MongoDB get_user error: {e}. Falling back to local store.")

    store = _read_local_store()
    return store.get("users", {}).get(u_clean)


def create_user(
    username: str,
    plain_password: str,
    role: str = "user",
    delay_seconds: int = 5,
    email: str = "",
) -> Dict[str, Any]:
    """Creates a new user with hashed password and initial zero counters."""
    u_clean = username.strip().lower()
    if not u_clean:
        raise ValueError("Username cannot be empty")
    if len(plain_password.strip()) < 4:
        raise ValueError("Password must be at least 4 characters")

    existing = get_user(u_clean)
    if existing:
        raise ValueError(f"User '{username}' already exists")

    hashed = hash_password(plain_password)
    delay_safe = max(2, int(delay_seconds))

    user_doc = {
        "username": u_clean,
        "password_hash": hashed,
        "role": role if role in ("admin", "user") else "user",
        "delay_seconds": delay_safe,
        "status": "Active",
        "email": email.strip(),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_applied": 0,
        "session_metadata": {
            "naukri": {"logged_in": False, "last_verified": None},
            "linkedin": {"logged_in": False, "last_verified": None},
        },
        "sheet_config": {"webhook_url": "", "sheet_url": "", "enabled": False},
    }

    # Ensure complete clean slate for newly created user across disk, db, and memory
    try:
        from common.paths import get_cache_path, get_session_path, RESUMES_DIR

        # Clean local cache file
        cache_path = get_cache_path(".applied_cache.json", username=u_clean)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"applied_keys": [], "history": []}, indent=2), encoding="utf-8"
        )

        # Clean old session files on disk
        for site in ("naukri", "linkedin"):
            sp = get_session_path(site, username=u_clean)
            if sp.exists():
                sp.unlink()

        # Clean old resume files on disk
        resume_p = RESUMES_DIR / f"{u_clean}_resume.pdf"
        if resume_p.exists():
            resume_p.unlink()

        # Clear in-memory session cache
        from common.login_helper import _SESSION_CACHE, _get_cache_key

        for site in ("naukri", "linkedin"):
            _SESSION_CACHE.pop(_get_cache_key(site, username=u_clean), None)

        # Clear engine manager user tracking
        from common.engine_manager import engine_manager

        engine_manager.reset_daily_limit("naukri", username=u_clean)
        engine_manager.reset_daily_limit("linkedin", username=u_clean)
        with engine_manager._lock:
            if u_clean in engine_manager._user_applied_counts:
                engine_manager._user_applied_counts[u_clean] = {
                    "naukri": 0,
                    "linkedin": 0,
                }
            if engine_manager._engine_active_user.get("naukri") == u_clean:
                engine_manager._engine_active_user["naukri"] = None
            if engine_manager._engine_active_user.get("linkedin") == u_clean:
                engine_manager._engine_active_user["linkedin"] = None
    except Exception as _ce:
        logger.debug(f"User '{u_clean}' initialization notice: {_ce}")

    db = get_db()
    if db is not None:
        try:
            db.users.update_one({"username": u_clean}, {"$set": user_doc}, upsert=True)
            db.user_profiles.delete_one({"username": u_clean})
            db.sessions.delete_many({"username": u_clean})
            db.activity.delete_many({"username": u_clean})
            try:
                import gridfs

                fs = gridfs.GridFS(db, collection="resumes_fs")
                for old in fs.find({"username": u_clean}):
                    fs.delete(old._id)
            except Exception:
                pass
            logger.info(f"Created user '{u_clean}' in MongoDB.")
        except Exception as e:
            logger.warning(
                f"Failed to create user in MongoDB: {e}. Saving to local store."
            )

    with _LOCK:
        store = _read_local_store()
        store.setdefault("users", {})[u_clean] = user_doc
        if u_clean in store.get("profiles", {}):
            del store["profiles"][u_clean]
        for s in ("naukri", "linkedin"):
            store.get("sessions", {}).pop(f"{u_clean}_{s}", None)
        _write_local_store(store)

    return user_doc


def list_users() -> List[Dict[str, Any]]:
    """Returns a list of all users without sensitive password hashes."""
    users_list = []
    db = get_db()
    if db is not None:
        try:
            for doc in db.users.find():
                doc["_id"] = str(doc["_id"])
                doc.pop("password_hash", None)
                users_list.append(doc)
            if users_list:
                return users_list
        except Exception as e:
            logger.warning(f"MongoDB list_users error: {e}")

    store = _read_local_store()
    for _, data in store.get("users", {}).items():
        clean_item = dict(data)
        clean_item.pop("password_hash", None)
        users_list.append(clean_item)
    return users_list


def delete_user(username: str) -> bool:
    """Deletes a user account. Admin user cannot be deleted."""
    u_clean = username.strip().lower()
    user = get_user(u_clean)
    if not user:
        return False
    if user.get("role") == "admin" or u_clean == settings.ADMIN_USERNAME:
        raise ValueError("Cannot delete the primary admin account")

    # Clean disk files
    try:
        from common.paths import get_cache_path, get_session_path, RESUMES_DIR

        cache_path = get_cache_path(".applied_cache.json", username=u_clean)
        if cache_path.exists():
            cache_path.unlink()
        for site in ("naukri", "linkedin"):
            sp = get_session_path(site, username=u_clean)
            if sp.exists():
                sp.unlink()
        resume_p = RESUMES_DIR / f"{u_clean}_resume.pdf"
        if resume_p.exists():
            resume_p.unlink()

        from common.login_helper import _SESSION_CACHE, _get_cache_key

        for site in ("naukri", "linkedin"):
            _SESSION_CACHE.pop(_get_cache_key(site, username=u_clean), None)

        from common.engine_manager import engine_manager

        engine_manager.reset_daily_limit("naukri", username=u_clean)
        engine_manager.reset_daily_limit("linkedin", username=u_clean)
        with engine_manager._lock:
            if u_clean in engine_manager._user_applied_counts:
                del engine_manager._user_applied_counts[u_clean]
            if engine_manager._engine_active_user.get("naukri") == u_clean:
                engine_manager._engine_active_user["naukri"] = None
            if engine_manager._engine_active_user.get("linkedin") == u_clean:
                engine_manager._engine_active_user["linkedin"] = None
    except Exception as _de:
        logger.debug(f"User cleanup notice: {_de}")

    db = get_db()
    if db is not None:
        try:
            db.users.delete_one({"username": u_clean})
            db.user_profiles.delete_one({"username": u_clean})
            db.sessions.delete_many({"username": u_clean})
            db.activity.delete_many({"username": u_clean})
            try:
                import gridfs

                fs = gridfs.GridFS(db, collection="resumes_fs")
                for old in fs.find({"username": u_clean}):
                    fs.delete(old._id)
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"MongoDB delete_user error: {e}")

    with _LOCK:
        store = _read_local_store()
        if u_clean in store.get("users", {}):
            del store["users"][u_clean]
        if u_clean in store.get("profiles", {}):
            del store["profiles"][u_clean]
        for s in ("naukri", "linkedin"):
            store.get("sessions", {}).pop(f"{u_clean}_{s}", None)
        _write_local_store(store)
    return True


def update_user_settings(
    username: str,
    delay_seconds: Optional[int] = None,
    stream_fps: Optional[int] = None,
    sheet_config: Optional[Dict[str, Any]] = None,
    session_metadata: Optional[Dict[str, Any]] = None,
    increment_applied: Optional[int] = None,
) -> bool:
    """Updates user delay (min safe 2s), stream FPS (1-60), Google sheet sync, or session metadata."""
    u_clean = username.strip().lower()
    user = get_user(u_clean)
    if not user:
        return False

    updates = {}
    if delay_seconds is not None:
        updates["delay_seconds"] = max(2, int(delay_seconds))
    if stream_fps is not None:
        updates["stream_fps"] = max(1, min(60, int(stream_fps)))
    if sheet_config is not None:
        current_sheet = user.get("sheet_config", {})
        current_sheet.update(sheet_config)
        updates["sheet_config"] = current_sheet
    if session_metadata is not None:
        current_meta = user.get("session_metadata", {})
        current_meta.update(session_metadata)
        updates["session_metadata"] = current_meta
    if increment_applied:
        updates["total_applied"] = user.get("total_applied", 0) + increment_applied

    if not updates:
        return True

    db = get_db()
    if db is not None:
        try:
            db.users.update_one({"username": u_clean}, {"$set": updates})
        except Exception as e:
            logger.warning(f"MongoDB update user settings error: {e}")

    with _LOCK:
        store = _read_local_store()
        if u_clean in store.get("users", {}):
            store["users"][u_clean].update(updates)
            _write_local_store(store)
    return True


def get_user_settings(username: str) -> Dict[str, Any]:
    """Retrieves user settings including delay, stream FPS, and sheet configuration."""
    user = get_user(username)
    if not user:
        return {
            "delay_seconds": 5,
            "stream_fps": 15,
            "sheet_config": {"webhook_url": "", "sheet_url": "", "enabled": False},
            "role": "user",
            "total_applied": 0,
        }
    return {
        "delay_seconds": user.get("delay_seconds", 5),
        "stream_fps": user.get("stream_fps", 15),
        "sheet_config": user.get(
            "sheet_config", {"webhook_url": "", "sheet_url": "", "enabled": False}
        ),
        "role": user.get("role", "user"),
        "total_applied": user.get("total_applied", 0),
        "created_at": user.get("created_at", ""),
    }


# ---------------------------------------------------------------------------
# Profile Data Access
# ---------------------------------------------------------------------------


def get_user_profile(username: str) -> Optional[Dict[str, Any]]:
    """Retrieves the profile document for a user."""
    u_clean = username.strip().lower()
    db = get_db()
    if db is not None:
        try:
            doc = db.user_profiles.find_one({"username": u_clean})
            if doc:
                doc["_id"] = str(doc["_id"])
                return doc
        except Exception as e:
            logger.warning(
                f"MongoDB get_user_profile error: {e}. Checking local store."
            )

    store = _read_local_store()
    return store.get("profiles", {}).get(u_clean)


def save_user_profile(username: str, profile_data: Dict[str, Any]) -> bool:
    """Saves or updates profile document for a user."""
    u_clean = username.strip().lower()
    if not u_clean:
        return False

    data = dict(profile_data)
    data["username"] = u_clean
    data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db = get_db()
    if db is not None:
        try:
            db.user_profiles.update_one(
                {"username": u_clean}, {"$set": data}, upsert=True
            )
            logger.info(f"Saved profile for user '{u_clean}' to MongoDB.")
        except Exception as e:
            logger.warning(
                f"MongoDB save_user_profile error: {e}. Saving to local store."
            )

    with _LOCK:
        store = _read_local_store()
        store.setdefault("profiles", {})[u_clean] = data
        _write_local_store(store)
    return True


def save_user_resume_meta(
    username: str, filename: str, file_path: str, size_bytes: int
) -> bool:
    """Updates resume metadata in user profile."""
    u_clean = username.strip().lower()
    meta = {
        "resume_file_name": filename,
        "resume_path": file_path,
        "resume_size_bytes": size_bytes,
        "resume_uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    db = get_db()
    if db is not None:
        try:
            db.user_profiles.update_one(
                {"username": u_clean}, {"$set": meta}, upsert=True
            )
        except Exception as e:
            logger.warning(f"MongoDB save_user_resume_meta error: {e}")

    with _LOCK:
        store = _read_local_store()
        prof = store.setdefault("profiles", {}).setdefault(
            u_clean, {"username": u_clean}
        )
        prof.update(meta)
        _write_local_store(store)
    return True


def is_user_profile_complete(username: str) -> tuple[bool, str, List[str]]:
    """Validates whether the user's profile has all required fields and uploaded resume."""
    u_clean = username.strip().lower()
    if not u_clean or u_clean == "admin":
        return True, "", []

    user = get_user(u_clean)
    if user and user.get("role") == "admin":
        return True, "", []

    prof = get_user_profile(u_clean)
    if not prof:
        return False, "Profile has not been created yet.", ["profile_created"]

    missing = []
    if not prof.get("current_city"):
        missing.append("Current City")

    if (
        prof.get("total_experience_years") is None
        or prof.get("total_experience_years") == ""
    ):
        missing.append("Total Experience (Years)")

    roles = prof.get("target_roles")
    if not roles or (isinstance(roles, list) and len(roles) == 0):
        missing.append("Target Roles")

    if prof.get("notice_period_days") is None or prof.get("notice_period_days") == "":
        missing.append("Notice Period (Days)")

    if prof.get("current_ctc_lpa") is None or prof.get("current_ctc_lpa") == "":
        missing.append("Current CTC (LPA)")

    if prof.get("expected_ctc_lpa") is None or prof.get("expected_ctc_lpa") == "":
        missing.append("Expected CTC (LPA)")

    resume_path = prof.get("resume_path")
    if not resume_path or not Path(resume_path).exists():
        missing.append("Resume PDF Upload")

    if missing:
        msg = f"Missing required fields: {', '.join(missing)}"
        return False, msg, missing

    return True, "", []


# ---------------------------------------------------------------------------
# Encrypted Session Cloud Storage (Prevents Session Loss on Render Restart)
# ---------------------------------------------------------------------------


def _get_current_quota_date() -> str:
    try:
        tz = ZoneInfo(settings.DAILY_LIMIT_TZ)
        return datetime.now(tz).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")


def save_encrypted_session(username: str, site: str, session_json_str: str) -> bool:
    """Encrypts and backs up browser session cookies to MongoDB with read-back verification."""
    u_clean = username.strip().lower()
    try:
        encrypted = encrypt_text(session_json_str)
    except Exception as e:
        raise RuntimeError(
            f"ENCRYPTION_KEY_INVALID: Failed to encrypt session payload: {e}"
        )

    data = {
        "username": u_clean,
        "site": site.lower(),
        "encrypted_payload": encrypted,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    is_prod = settings.ENV == "production"
    db = get_db()

    if is_prod:
        if db is None:
            raise RuntimeError(
                "MONGO_UNREACHABLE: MongoDB connection is unavailable in production. Cannot persist session."
            )
        try:
            db.sessions.update_one(
                {"username": u_clean, "site": site.lower()}, {"$set": data}, upsert=True
            )
            # Read-back verification
            doc = db.sessions.find_one({"username": u_clean, "site": site.lower()})
            if not doc or not doc.get("encrypted_payload"):
                raise RuntimeError(
                    "SESSION_VERIFICATION_FAILED: Session was not found after write."
                )
            decrypted = decrypt_text(doc["encrypted_payload"])
            if decrypted != session_json_str:
                raise RuntimeError(
                    "SESSION_VERIFICATION_FAILED: Decrypted session did not match original."
                )
            return True
        except Exception as e:
            err_msg = str(e)
            if "auth" in err_msg.lower():
                raise RuntimeError(f"MONGO_AUTH_FAILED: {e}")
            if (
                "unreachable" in err_msg
                or "timeout" in err_msg.lower()
                or "connection" in err_msg.lower()
            ):
                raise RuntimeError(f"MONGO_UNREACHABLE: {e}")
            if "SESSION_VERIFICATION" in err_msg:
                raise
            raise RuntimeError(f"MONGO_WRITE_FAILED: {e}")

    # Local / dev mode with optional Mongo and readback verification
    if db is not None:
        try:
            db.sessions.update_one(
                {"username": u_clean, "site": site.lower()}, {"$set": data}, upsert=True
            )
            doc = db.sessions.find_one({"username": u_clean, "site": site.lower()})
            if doc and doc.get("encrypted_payload"):
                decrypted = decrypt_text(doc["encrypted_payload"])
                if decrypted == session_json_str:
                    return True
        except Exception as e:
            logger.warning(f"Error backing up session to MongoDB: {e}")

    with _LOCK:
        store = _read_local_store()
        key = f"{u_clean}_{site.lower()}"
        store.setdefault("sessions", {})[key] = data
        _write_local_store(store)
    return True


def get_decrypted_session(username: str, site: str) -> Optional[str]:
    """Retrieves and decrypts browser session cookies from MongoDB."""
    u_clean = username.strip().lower()
    db = get_db()
    if db is not None:
        try:
            doc = db.sessions.find_one({"username": u_clean, "site": site.lower()})
            if doc and doc.get("encrypted_payload"):
                return decrypt_text(doc["encrypted_payload"])
        except Exception as e:
            logger.warning(f"Error reading session from MongoDB: {e}")

    store = _read_local_store()
    key = f"{u_clean}_{site.lower()}"
    saved = store.get("sessions", {}).get(key)
    if saved and saved.get("encrypted_payload"):
        return decrypt_text(saved["encrypted_payload"])
    return None


# ---------------------------------------------------------------------------
# Daily Limit Counter Collection (Independent of Activity Logs)
# ---------------------------------------------------------------------------


def get_daily_applied_count(
    username: str, site: str, date_str: Optional[str] = None
) -> int:
    """Returns today's applied job count from the daily_limits collection."""
    u_clean = username.strip().lower()
    d_str = date_str or _get_current_quota_date()
    db = get_db()
    if db is not None:
        try:
            doc = db.daily_limits.find_one(
                {"username": u_clean, "site": site.lower(), "date": d_str}
            )
            if doc:
                return int(doc.get("count", 0))
        except Exception as e:
            logger.warning(f"Error reading daily limit from MongoDB: {e}")

    with _LOCK:
        store = _read_local_store()
        key = f"{u_clean}_{site.lower()}_{d_str}"
        return int(store.get("daily_limits", {}).get(key, 0))


def increment_daily_applied_count(
    username: str, site: str, delta: int = 1, date_str: Optional[str] = None
) -> int:
    """Increments today's applied job count in daily_limits collection."""
    u_clean = username.strip().lower()
    d_str = date_str or _get_current_quota_date()
    db = get_db()
    if db is not None:
        try:
            res = db.daily_limits.find_one_and_update(
                {"username": u_clean, "site": site.lower(), "date": d_str},
                {
                    "$inc": {"count": delta},
                    "$set": {
                        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    },
                },
                upsert=True,
                return_document=pymongo.ReturnDocument.AFTER,
            )
            if res:
                return int(res.get("count", delta))
        except Exception as e:
            logger.warning(f"Error updating daily limit in MongoDB: {e}")

    with _LOCK:
        store = _read_local_store()
        key = f"{u_clean}_{site.lower()}_{d_str}"
        cur = int(store.setdefault("daily_limits", {}).get(key, 0))
        cur += delta
        store["daily_limits"][key] = cur
        _write_local_store(store)
        return cur


def is_daily_limit_reached(
    username: str, site: str, limit: int = 50, date_str: Optional[str] = None
) -> bool:
    """Checks if the user has reached their daily application quota for the specified site."""
    return get_daily_applied_count(username, site, date_str) >= limit


def reset_daily_applied_count(username: str, site: str, date_str: Optional[str] = None):
    """Resets the daily application quota count."""
    u_clean = username.strip().lower()
    d_str = date_str or _get_current_quota_date()
    db = get_db()
    if db is not None:
        try:
            db.daily_limits.delete_many(
                {"username": u_clean, "site": site.lower(), "date": d_str}
            )
        except Exception as e:
            logger.warning(f"Error deleting daily limit in MongoDB: {e}")

    with _LOCK:
        store = _read_local_store()
        key = f"{u_clean}_{site.lower()}_{d_str}"
        store.setdefault("daily_limits", {}).pop(key, None)
        _write_local_store(store)


# ---------------------------------------------------------------------------
# Centralized Status Precedence
# ---------------------------------------------------------------------------


def compute_engine_status(
    site: str,
    username: str,
    has_session: bool,
    is_profile_complete: bool,
    is_busy: bool = False,
    busy_user: str = "",
    is_limit_reached: bool = False,
    is_running: bool = False,
    is_recovering: bool = False,
    is_paused: bool = False,
    custom_reason: str = "",
) -> Tuple[str, str]:
    """
    Enforces strict status precedence across both portals:
    1. Session Missing / Removed / Expired
    2. Profile Incomplete
    3. Busy (running for another user)
    4. Limit Reached (Daily quota reached)
    5. Recovering / Paused
    6. Running
    7. Stopped
    """
    title_site = site.title()

    # Precedence 1: Missing Session (Highest precedence, even above Limit Reached)
    if not has_session:
        return (
            "Session Missing",
            f"Missing {title_site} session. Use 'Add Session' to log in.",
        )

    # Precedence 2: Profile Incomplete
    if not is_profile_complete:
        return (
            "Profile Incomplete",
            "Please complete your profile before starting automation.",
        )

    # Precedence 3: Busy
    if is_busy:
        return (
            "Busy",
            f"Engine is currently running for user '{busy_user}'.",
        )

    # Precedence 4: Daily Limit Reached
    if is_limit_reached:
        return (
            "Limit Reached",
            custom_reason
            or f"Daily quota reached for {title_site} — resets at 12:00 AM.",
        )

    # Precedence 5: Recovering or Low-memory Paused
    if is_recovering:
        return ("Recovering", "Browser auto-recovery in progress...")
    if is_paused:
        return ("Paused", "Engine paused.")

    # Precedence 6: Running
    if is_running:
        return ("Running", f"{title_site} engine is running and monitoring jobs.")

    # Precedence 7: Stopped (Default)
    return ("Stopped", "Engine stopped.")


def delete_encrypted_session(username: str, site: str) -> bool:
    """Deletes browser session cookies from MongoDB and local store."""
    u_clean = username.strip().lower()
    site_clean = site.lower().strip()
    deleted = False

    db = get_db()
    if db is not None:
        try:
            res = db.sessions.delete_one({"username": u_clean, "site": site_clean})
            if res.deleted_count > 0:
                deleted = True
        except Exception as e:
            logger.warning(f"Error deleting session from MongoDB: {e}")

    with _LOCK:
        store = _read_local_store()
        key = f"{u_clean}_{site_clean}"
        if "sessions" in store and key in store["sessions"]:
            del store["sessions"][key]
            _write_local_store(store)
            deleted = True

    return deleted


def check_storage_health() -> Dict[str, Any]:
    """
    Diagnostic storage health check:
    1. Ping MongoDB or local store.
    2. Write, read, delete round-trip test.
    3. Symmetric Fernet encryption/decryption round-trip test.
    """
    db = get_db()
    is_prod = settings.ENV == "production"
    health: Dict[str, Any] = {
        "status": "ok",
        "storage_type": "mongodb" if db is not None else "local_store",
        "ping_ms": 0.0,
        "db_roundtrip_ms": 0.0,
        "crypto_roundtrip_ms": 0.0,
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # 1. DB Ping & Read-Write-Delete Roundtrip
    t0 = time.perf_counter()
    if db is not None:
        try:
            db.command("ping")
            health["ping_ms"] = round((time.perf_counter() - t0) * 1000, 2)

            t1 = time.perf_counter()
            test_doc = {
                "test_key": "health_probe",
                "ts": time.time(),
            }
            db.system_health_checks.insert_one(test_doc)
            found = db.system_health_checks.find_one({"test_key": "health_probe"})
            db.system_health_checks.delete_one({"test_key": "health_probe"})
            if not found:
                raise RuntimeError("Health check write/read roundtrip document missing")
            health["db_roundtrip_ms"] = round((time.perf_counter() - t1) * 1000, 2)
        except Exception as e:
            health["status"] = "degraded" if not is_prod else "error"
            health["db_error"] = str(e)
    else:
        # Local store roundtrip
        if is_prod:
            health["status"] = "error"
            health["db_error"] = "MONGO_UNREACHABLE: MongoDB connection required in production"
        else:
            t1 = time.perf_counter()
            with _LOCK:
                store = _read_local_store()
                store["_health_probe"] = time.time()
                _write_local_store(store)
                del store["_health_probe"]
                _write_local_store(store)
            health["db_roundtrip_ms"] = round((time.perf_counter() - t1) * 1000, 2)

    # 2. Crypto Roundtrip
    t2 = time.perf_counter()
    try:
        sample_secret = "probe_secret_token_12345"
        enc = encrypt_text(sample_secret)
        dec = decrypt_text(enc)
        if dec != sample_secret:
            raise RuntimeError("Decrypted text did not match original secret")
        health["crypto_roundtrip_ms"] = round((time.perf_counter() - t2) * 1000, 2)
    except Exception as ce:
        health["status"] = "error"
        health["crypto_error"] = str(ce)

    return health


def init_db():
    """Initializes DB connection, ensures indexes, and creates or updates default Admin user."""
    admin_user = settings.ADMIN_USERNAME.strip().lower()
    admin_pass = settings.ADMIN_PASSWORD

    existing_admin = get_user(admin_user)
    if not existing_admin:
        logger.info(f"Seeding primary admin user '{admin_user}'...")
        create_user(admin_user, admin_pass, role="admin", delay_seconds=5)
    else:
        # Check if stored hash matches currently configured ADMIN_PASSWORD
        stored_hash = existing_admin.get("password_hash", "")
        from backend.app.core.security import verify_password, hash_password

        if admin_pass and not verify_password(admin_pass, stored_hash):
            logger.warning(
                f"[Security] ADMIN_PASSWORD in environment does not match stored hash for '{admin_user}'. "
                "Updating hash and invalidating prior sessions/tokens."
            )
            new_hash = hash_password(admin_pass)
            new_token_version = int(existing_admin.get("token_version", 1)) + 1
            db = get_db()
            if db is not None:
                try:
                    db.users.update_one(
                        {"username": admin_user},
                        {
                            "$set": {
                                "password_hash": new_hash,
                                "token_version": new_token_version,
                                "updated_at": datetime.now().strftime(
                                    "%Y-%m-%d %H:%M:%S"
                                ),
                            }
                        },
                    )
                except Exception as ue:
                    logger.warning(f"Failed to update admin password in MongoDB: {ue}")

            with _LOCK:
                store = _read_local_store()
                if admin_user in store.get("users", {}):
                    store["users"][admin_user]["password_hash"] = new_hash
                    store["users"][admin_user]["token_version"] = new_token_version
                    _write_local_store(store)

            logger.info(
                f"Rotated password and invalidated prior tokens for admin user '{admin_user}' (token_version={new_token_version})."
            )
        else:
            logger.info(f"Primary admin user '{admin_user}' verified.")


init_default_admin = init_db

# Initialize DB on module import
try:
    init_db()
except Exception as _e:
    logger.warning(f"Initial DB check warning: {_e}")
