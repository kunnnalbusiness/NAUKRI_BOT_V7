"""
Common Database Adapter.
Thin compatibility wrapper pointing directly to backend.app.db.mongo as the
single, unified source of truth for MongoDB connections, security hashing,
and isolated user data access.
"""

from backend.app.core.security import (
    hash_password,
    verify_password,
    verify_password as verify_password_hash,
)
from backend.app.db.mongo import (
    get_db,
    get_user,
    create_user,
    list_users,
    delete_user,
    update_user_settings,
    get_user_settings,
    get_user_profile,
    save_user_profile,
    save_user_resume_meta,
    is_user_profile_complete,
    init_default_admin,
    init_default_admin as init_db,
)

__all__ = [
    "get_db",
    "hash_password",
    "verify_password",
    "verify_password_hash",
    "get_user",
    "create_user",
    "list_users",
    "delete_user",
    "update_user_settings",
    "get_user_settings",
    "get_user_profile",
    "save_user_profile",
    "save_user_resume_meta",
    "is_user_profile_complete",
    "init_default_admin",
    "init_db",
]
