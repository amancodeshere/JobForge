"""User-scoped persistence contracts for the public JobForge beta."""

from app.persistence.models import SavedJobState, UserIdentity
from app.persistence.repository import PersistenceError, UserRepository
from app.persistence.sqlite_repository import SQLiteUserRepository

__all__ = [
    "PersistenceError",
    "SavedJobState",
    "SQLiteUserRepository",
    "UserIdentity",
    "UserRepository",
]
