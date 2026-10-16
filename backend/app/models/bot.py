"""
Automation Engine and AI Key Models.
"""

from typing import Optional
from pydantic import BaseModel


class StartEngineRequest(BaseModel):
    only_fresh_10min: bool = False
    only_fresh: Optional[bool] = None
    fresh_threshold_minutes: Optional[int] = 10


class FreshFilterRequest(BaseModel):
    enabled: bool = True
    threshold_minutes: int = 10


class AddKeyRequest(BaseModel):
    provider: str
    key: str
    enabled: bool = True


class UpdateKeyRequest(BaseModel):
    enabled: bool


class SheetSettingsRequest(BaseModel):
    webhook_url: str = ""
    sheet_url: str = ""
