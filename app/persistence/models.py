from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class SavedJobState(str, Enum):
    SAVED = "saved"
    DISMISSED = "dismissed"
    APPLIED = "applied"


class UserIdentity(BaseModel):
    """Identity claims received from the authentication provider."""

    subject: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(default="Member", min_length=1, max_length=160)


class StoredUser(BaseModel):
    id: str
    auth_subject: str
    email: str
    display_name: str
    onboarding_completed: bool = False


class StoredCVDocument(BaseModel):
    id: str
    user_id: str
    storage_key: str
    original_filename: str
    content_type: str
    byte_size: int
    checksum: str
    is_active: bool


class StoredSearchRun(BaseModel):
    id: str
    user_id: str
    status: str
    result_count: int


class StoredApplication(BaseModel):
    id: str
    user_id: str
    job_id: str
    cv_document_id: str
    status: str
