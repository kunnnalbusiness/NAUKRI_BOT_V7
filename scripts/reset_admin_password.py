"""
CLI utility to securely rotate the Admin password, update MongoDB,
and invalidate all existing admin JWT sessions.
Usage: python scripts/reset_admin_password.py <new_password>
"""

import sys
from datetime import datetime
from backend.app.core.config import settings
from backend.app.core.security import hash_password
from backend.app.db.mongo import get_db, _read_local_store, _write_local_store, _LOCK, get_user


def reset_admin_password(new_password: str) -> bool:
    new_pass = new_password.strip()
    if len(new_pass) < 6:
        print("[ERROR] Password must be at least 6 characters.")
        return False

    admin_username = settings.ADMIN_USERNAME.strip().lower()
    user = get_user(admin_username)
    new_hash = hash_password(new_pass)
    new_version = (int(user.get("token_version", 1)) if user else 1) + 1

    db = get_db()
    if db is not None:
        try:
            db.users.update_one(
                {"username": admin_username},
                {
                    "$set": {
                        "password_hash": new_hash,
                        "token_version": new_version,
                        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                },
                upsert=True,
            )
        except Exception as e:
            print(f"[ERROR] Failed to update MongoDB: {e}")
            return False

    with _LOCK:
        store = _read_local_store()
        if admin_username in store.get("users", {}):
            store["users"][admin_username]["password_hash"] = new_hash
            store["users"][admin_username]["token_version"] = new_version
            store["users"][admin_username]["updated_at"] = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            _write_local_store(store)

    print(
        f"[SUCCESS] Admin password updated successfully. Prior tokens invalidated (token_version={new_version})."
    )
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/reset_admin_password.py <new_password>")
        sys.exit(1)

    ok = reset_admin_password(sys.argv[1])
    sys.exit(0 if ok else 1)
