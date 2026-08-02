from __future__ import annotations

from typing import Protocol

from app.persistence.models import (
    SavedJobState,
    StoredApplication,
    StoredCVDocument,
    StoredSearchRun,
    StoredUser,
    UserIdentity,
)


class PersistenceError(RuntimeError):
    """Raised when a user-scoped resource is missing or ownership is invalid."""


class UserRepository(Protocol):
    """Persistence boundary. Every private operation requires an owner ID."""

    def upsert_user(self, identity: UserIdentity) -> StoredUser: ...

    def save_cv_metadata(
        self,
        user_id: str,
        *,
        storage_key: str,
        original_filename: str,
        content_type: str,
        byte_size: int,
        checksum: str,
        make_active: bool = True,
    ) -> StoredCVDocument: ...

    def get_cv_document(self, user_id: str, document_id: str) -> StoredCVDocument: ...

    def save_preferences(self, user_id: str, payload: dict) -> str: ...

    def get_active_preferences(self, user_id: str) -> dict | None: ...

    def create_search_run(
        self,
        user_id: str,
        *,
        preferences_id: str | None,
        input_payload: dict,
        result_payload: dict,
        status: str,
    ) -> StoredSearchRun: ...

    def get_search_run(self, user_id: str, search_run_id: str) -> StoredSearchRun: ...

    def upsert_job_listing(self, job_id: str, canonical_url: str, payload: dict) -> None: ...

    def set_saved_job_state(
        self, user_id: str, job_id: str, state: SavedJobState, note: str = ""
    ) -> None: ...

    def list_saved_jobs(self, user_id: str) -> list[tuple[str, SavedJobState, str]]: ...

    def save_application_metadata(
        self,
        user_id: str,
        *,
        job_id: str,
        cv_document_id: str,
        status: str,
        payload: dict,
    ) -> StoredApplication: ...

    def get_application(self, user_id: str, application_id: str) -> StoredApplication: ...

    def export_user_data(self, user_id: str) -> dict: ...
