from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.persistence.models import (
    SavedJobState,
    StoredApplication,
    StoredCVDocument,
    StoredSearchRun,
    StoredUser,
    UserIdentity,
)
from app.persistence.repository import PersistenceError


class SQLiteUserRepository:
    """Local test implementation mirroring the production ownership contract.

    This adapter stores metadata only. Production uses the Postgres migration in
    ``supabase/migrations`` and private object storage for document bytes.
    """

    def __init__(self, database_path: str | Path = ":memory:") -> None:
        self.connection = sqlite3.connect(str(database_path))
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def close(self) -> None:
        self.connection.close()

    def upsert_user(self, identity: UserIdentity) -> StoredUser:
        row = self.connection.execute(
            "SELECT * FROM users WHERE auth_subject = ?", (identity.subject,)
        ).fetchone()
        now = _now()
        if row:
            self.connection.execute(
                "UPDATE users SET email = ?, display_name = ?, last_active_at = ? WHERE id = ?",
                (identity.email, identity.display_name, now, row["id"]),
            )
            self.connection.commit()
            return self._stored_user(self.connection.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone())
        user_id = _id()
        self.connection.execute(
            "INSERT INTO users (id, auth_subject, email, display_name, created_at, last_active_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, identity.subject, identity.email, identity.display_name, now, now),
        )
        self.connection.commit()
        return StoredUser(id=user_id, auth_subject=identity.subject, email=identity.email, display_name=identity.display_name)

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
    ) -> StoredCVDocument:
        self._require_user(user_id)
        if not storage_key.startswith(f"users/{user_id}/"):
            raise PersistenceError("Document storage keys must be scoped to the owner.")
        if byte_size < 1 or byte_size > 20_000_000:
            raise PersistenceError("Document size is outside the permitted range.")
        if make_active:
            self.connection.execute("UPDATE cv_documents SET is_active = 0 WHERE user_id = ?", (user_id,))
        document = StoredCVDocument(
            id=_id(),
            user_id=user_id,
            storage_key=storage_key,
            original_filename=original_filename,
            content_type=content_type,
            byte_size=byte_size,
            checksum=checksum,
            is_active=make_active,
        )
        self.connection.execute(
            "INSERT INTO cv_documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (*document.model_dump().values(), _now()),
        )
        self.connection.commit()
        return document

    def get_cv_document(self, user_id: str, document_id: str) -> StoredCVDocument:
        row = self.connection.execute(
            "SELECT * FROM cv_documents WHERE id = ? AND user_id = ?", (document_id, user_id)
        ).fetchone()
        if not row:
            raise PersistenceError("CV document was not found for this user.")
        return self._stored_document(row)

    def save_preferences(self, user_id: str, payload: dict) -> str:
        self._require_user(user_id)
        self.connection.execute("UPDATE search_preferences SET is_active = 0 WHERE user_id = ?", (user_id,))
        preference_id = _id()
        self.connection.execute(
            "INSERT INTO search_preferences VALUES (?, ?, ?, ?, ?)",
            (preference_id, user_id, json.dumps(payload, sort_keys=True), 1, _now()),
        )
        self.connection.commit()
        return preference_id

    def get_active_preferences(self, user_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT payload FROM search_preferences WHERE user_id = ? AND is_active = 1", (user_id,)
        ).fetchone()
        return json.loads(row["payload"]) if row else None

    def create_search_run(
        self,
        user_id: str,
        *,
        preferences_id: str | None,
        input_payload: dict,
        result_payload: dict,
        status: str,
    ) -> StoredSearchRun:
        self._require_user(user_id)
        if preferences_id:
            self._require_owned("search_preferences", preferences_id, user_id)
        search = StoredSearchRun(id=_id(), user_id=user_id, status=status, result_count=len(result_payload.get("ranked_jobs", [])))
        self.connection.execute(
            "INSERT INTO search_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (search.id, user_id, preferences_id, status, json.dumps(input_payload, sort_keys=True), json.dumps(result_payload, sort_keys=True), search.result_count, _now()),
        )
        self.connection.commit()
        return search

    def get_search_run(self, user_id: str, search_run_id: str) -> StoredSearchRun:
        row = self.connection.execute(
            "SELECT * FROM search_runs WHERE id = ? AND user_id = ?", (search_run_id, user_id)
        ).fetchone()
        if not row:
            raise PersistenceError("Search run was not found for this user.")
        return StoredSearchRun(id=row["id"], user_id=row["user_id"], status=row["status"], result_count=row["result_count"])

    def upsert_job_listing(self, job_id: str, canonical_url: str, payload: dict) -> None:
        self.connection.execute(
            "INSERT INTO job_listings VALUES (?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET canonical_url = excluded.canonical_url, payload = excluded.payload, updated_at = excluded.updated_at",
            (job_id, canonical_url, json.dumps(payload, sort_keys=True), _now()),
        )
        self.connection.commit()

    def set_saved_job_state(self, user_id: str, job_id: str, state: SavedJobState, note: str = "") -> None:
        self._require_user(user_id)
        if not self.connection.execute("SELECT 1 FROM job_listings WHERE id = ?", (job_id,)).fetchone():
            raise PersistenceError("Job listing does not exist.")
        self.connection.execute(
            "INSERT INTO saved_jobs VALUES (?, ?, ?, ?, ?) ON CONFLICT(user_id, job_id) DO UPDATE SET state = excluded.state, note = excluded.note, updated_at = excluded.updated_at",
            (user_id, job_id, state.value, note[:2_000], _now()),
        )
        self.connection.commit()

    def list_saved_jobs(self, user_id: str) -> list[tuple[str, SavedJobState, str]]:
        rows = self.connection.execute(
            "SELECT job_id, state, note FROM saved_jobs WHERE user_id = ? ORDER BY updated_at DESC", (user_id,)
        ).fetchall()
        return [(row["job_id"], SavedJobState(row["state"]), row["note"]) for row in rows]

    def save_application_metadata(
        self,
        user_id: str,
        *,
        job_id: str,
        cv_document_id: str,
        status: str,
        payload: dict,
    ) -> StoredApplication:
        self._require_user(user_id)
        self.get_cv_document(user_id, cv_document_id)
        if not self.connection.execute("SELECT 1 FROM job_listings WHERE id = ?", (job_id,)).fetchone():
            raise PersistenceError("Job listing does not exist.")
        application = StoredApplication(id=_id(), user_id=user_id, job_id=job_id, cv_document_id=cv_document_id, status=status)
        self.connection.execute(
            "INSERT INTO applications VALUES (?, ?, ?, ?, ?, ?, ?)",
            (application.id, user_id, job_id, cv_document_id, status, json.dumps(payload, sort_keys=True), _now()),
        )
        self.connection.commit()
        return application

    def get_application(self, user_id: str, application_id: str) -> StoredApplication:
        row = self.connection.execute(
            "SELECT * FROM applications WHERE id = ? AND user_id = ?", (application_id, user_id)
        ).fetchone()
        if not row:
            raise PersistenceError("Application was not found for this user.")
        return StoredApplication(id=row["id"], user_id=row["user_id"], job_id=row["job_id"], cv_document_id=row["cv_document_id"], status=row["status"])

    def export_user_data(self, user_id: str) -> dict:
        user = self._require_user(user_id)
        return {
            "user": user.model_dump(),
            "cv_documents": [self._stored_document(row).model_dump() for row in self.connection.execute("SELECT * FROM cv_documents WHERE user_id = ?", (user_id,))],
            "preferences": self.get_active_preferences(user_id),
            "search_runs": [dict(row) for row in self.connection.execute("SELECT id, status, result_count, created_at FROM search_runs WHERE user_id = ?", (user_id,))],
            "saved_jobs": [{"job_id": job_id, "state": state.value, "note": note} for job_id, state, note in self.list_saved_jobs(user_id)],
            "applications": [dict(row) for row in self.connection.execute("SELECT id, job_id, cv_document_id, status, created_at FROM applications WHERE user_id = ?", (user_id,))],
        }

    def _require_user(self, user_id: str) -> StoredUser:
        row = self.connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise PersistenceError("User was not found.")
        return self._stored_user(row)

    def _require_owned(self, table: str, record_id: str, user_id: str) -> None:
        if table not in {"search_preferences"}:
            raise PersistenceError("Unsupported ownership check.")
        row = self.connection.execute(f"SELECT 1 FROM {table} WHERE id = ? AND user_id = ?", (record_id, user_id)).fetchone()
        if not row:
            raise PersistenceError("Resource was not found for this user.")

    def _initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, auth_subject TEXT UNIQUE NOT NULL, email TEXT NOT NULL, display_name TEXT NOT NULL, onboarding_completed INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, last_active_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cv_documents (id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, storage_key TEXT UNIQUE NOT NULL, original_filename TEXT NOT NULL, content_type TEXT NOT NULL, byte_size INTEGER NOT NULL, checksum TEXT NOT NULL, is_active INTEGER NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS search_preferences (id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, payload TEXT NOT NULL, is_active INTEGER NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS search_runs (id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, preferences_id TEXT REFERENCES search_preferences(id), status TEXT NOT NULL, input_payload TEXT NOT NULL, result_payload TEXT NOT NULL, result_count INTEGER NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS job_listings (id TEXT PRIMARY KEY, canonical_url TEXT UNIQUE NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS saved_jobs (user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, job_id TEXT NOT NULL REFERENCES job_listings(id) ON DELETE CASCADE, state TEXT NOT NULL, note TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(user_id, job_id));
            CREATE TABLE IF NOT EXISTS applications (id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, job_id TEXT NOT NULL REFERENCES job_listings(id), cv_document_id TEXT NOT NULL REFERENCES cv_documents(id), status TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
            """
        )
        self.connection.commit()

    @staticmethod
    def _stored_user(row: sqlite3.Row) -> StoredUser:
        return StoredUser(id=row["id"], auth_subject=row["auth_subject"], email=row["email"], display_name=row["display_name"], onboarding_completed=bool(row["onboarding_completed"]))

    @staticmethod
    def _stored_document(row: sqlite3.Row) -> StoredCVDocument:
        return StoredCVDocument(id=row["id"], user_id=row["user_id"], storage_key=row["storage_key"], original_filename=row["original_filename"], content_type=row["content_type"], byte_size=row["byte_size"], checksum=row["checksum"], is_active=bool(row["is_active"]))


def _id() -> str:
    return str(uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
