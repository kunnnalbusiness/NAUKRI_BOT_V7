"""
Admin User Management API Router.
Strictly restricted to users possessing the 'admin' role.
"""

from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException

from backend.app.core.dependencies import require_admin, require_csrf
from backend.app.db.mongo import list_users, create_user, delete_user
from backend.app.models.user import AdminCreateUserRequest, UserOut

router = APIRouter(prefix="/admin", tags=["Admin Operations"])


@router.get("/users", response_model=List[UserOut])
async def admin_list_users(_claims: Dict[str, str] = Depends(require_admin)):
    """Admin only: list all registered user accounts and summary metrics."""
    return list_users()


@router.post("/users")
async def admin_create_user(
    body: AdminCreateUserRequest,
    _claims: Dict[str, str] = Depends(require_admin),
    _csrf: bool = Depends(require_csrf),
):
    """Admin only: creates a new isolated user account with bcrypt password hash."""
    u_clean = body.username.strip().lower()
    if not u_clean:
        raise HTTPException(status_code=400, detail="Username cannot be empty")
    if len(body.password) < 4:
        raise HTTPException(
            status_code=400, detail="Password must be at least 4 characters"
        )

    try:
        new_user = create_user(
            username=u_clean,
            plain_password=body.password,
            role=body.role if body.role in ("admin", "user") else "user",
            delay_seconds=max(2, int(body.delay_seconds)),
            email=body.email or "",
        )
        new_user.pop("password_hash", None)
        return {"success": True, "user": new_user}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.delete("/users/{username}")
async def admin_delete_user(
    username: str,
    _claims: Dict[str, str] = Depends(require_admin),
    _csrf: bool = Depends(require_csrf),
):
    """Admin only: deletes a user account and associated profile/sessions."""
    try:
        ok = delete_user(username)
        if not ok:
            raise HTTPException(status_code=404, detail="User not found")
        return {"success": True, "message": f"User '{username}' deleted successfully."}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
