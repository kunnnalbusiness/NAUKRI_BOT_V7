"""
User and Authentication Pydantic Models.
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: Optional[str] = "admin"
    password: str


class LoginResponse(BaseModel):
    success: bool
    token: str
    csrf_token: str
    username: str
    role: str


class AdminCreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=40)
    password: str = Field(..., min_length=4)
    role: str = "user"
    delay_seconds: int = Field(5, ge=2, le=120)
    stream_fps: int = Field(15, ge=1, le=60)
    email: Optional[str] = ""


class UserOut(BaseModel):
    username: str
    role: str
    delay_seconds: int
    stream_fps: Optional[int] = 15
    status: str
    email: Optional[str] = ""
    created_at: Optional[str] = ""
    total_applied: Optional[int] = 0


class UserSettingsUpdate(BaseModel):
    delay_seconds: Optional[int] = Field(None, ge=2, le=120)
    stream_fps: Optional[int] = Field(None, ge=1, le=60)
    webhook_url: Optional[str] = None
    sheet_url: Optional[str] = None


class UserSettingsOut(BaseModel):
    delay_seconds: int
    stream_fps: int = 15
    sheet_config: Dict[str, Any]
    role: str
    created_at: Optional[str] = ""
    total_applied: Optional[int] = 0
