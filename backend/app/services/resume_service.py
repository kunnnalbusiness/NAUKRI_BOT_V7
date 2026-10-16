"""
Resume Upload, Validation, Security Sanitization, and Storage Service.
"""

import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
from fastapi import UploadFile, HTTPException, status
from fastapi.responses import FileResponse

from backend.app.core.config import settings
from backend.app.db.mongo import (
    save_user_resume_meta,
    get_user_profile,
    is_user_profile_complete,
)

MAX_RESUME_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


async def handle_resume_upload(file: UploadFile, username: str) -> Dict[str, Any]:
    """
    Validates PDF file, enforces 5MB limit, sanitizes filename,
    saves to user folder, and updates profile metadata.
    """
    u_clean = username.strip().lower()
    filename = file.filename or "resume.pdf"

    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF documents are allowed (.pdf).",
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty."
        )

    # Magic-byte check: extension alone is not proof of a real PDF
    if not content.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content is not a valid PDF document.",
        )

    if len(content) > MAX_RESUME_SIZE_BYTES:
        mb = round(len(content) / (1024 * 1024), 2)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds maximum allowed size of 5 MB ({mb} MB).",
        )

    # Sanitize filename against directory traversal
    clean_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", Path(filename).name)
    if not clean_name.lower().endswith(".pdf"):
        clean_name += ".pdf"

    user_dir = settings.DATA_DIR / "resumes" / u_clean
    user_dir.mkdir(parents=True, exist_ok=True)

    # Clean old files to ensure single active resume
    for old_file in user_dir.glob("*"):
        try:
            if old_file.is_file():
                old_file.unlink()
        except Exception:
            pass

    dest_path = user_dir / clean_name
    dest_path.write_bytes(content)

    # Save to MongoDB GridFS for persistent cloud storage across container reboots
    from backend.app.db.mongo import save_resume_gridfs

    save_resume_gridfs(u_clean, clean_name, content)

    # Update MongoDB metadata
    save_user_resume_meta(u_clean, clean_name, str(dest_path), len(content))

    is_complete, reason, missing = is_user_profile_complete(u_clean)
    return {
        "success": True,
        "message": f"Resume '{clean_name}' successfully uploaded ({round(len(content)/(1024*1024), 2)} MB).",
        "filename": clean_name,
        "size_bytes": len(content),
        "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "is_complete": is_complete,
        "missing_fields": missing,
    }


def get_resume_download(username: str) -> FileResponse:
    """Returns a FileResponse for downloading or previewing user's resume, restoring from GridFS if needed."""
    u_clean = username.strip().lower()
    prof = get_user_profile(u_clean)

    user_dir = (settings.DATA_DIR / "resumes" / u_clean).resolve()
    user_dir.mkdir(parents=True, exist_ok=True)

    # 1. Try local disk path if recorded
    resume_path = None
    if prof and prof.get("resume_path"):
        p = Path(prof["resume_path"]).resolve()
        if p.exists():
            resume_path = p

    # 2. Try restoring from MongoDB GridFS if local file is missing (e.g. Render container restart)
    if not resume_path:
        from backend.app.db.mongo import get_resume_gridfs

        gridfs_res = get_resume_gridfs(u_clean)
        if gridfs_res:
            fname, file_bytes = gridfs_res
            restored_path = user_dir / fname
            restored_path.write_bytes(file_bytes)
            resume_path = restored_path

    # 3. Fallback for admin local file
    if not resume_path and u_clean == "admin":
        from common.paths import get_resume_path

        p = get_resume_path()
        if p.exists():
            resume_path = p

    if not resume_path or not resume_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No resume uploaded yet."
        )

    return FileResponse(
        str(resume_path), media_type="application/pdf", filename=resume_path.name
    )
