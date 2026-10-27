"""Server-side access decisions; identity comes only from Streamlit OIDC."""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from time import time


def authenticated_subject(claims: Mapping, *, now: float | None = None) -> str | None:
    if not claims.get("is_logged_in"):
        return None
    subject = claims.get("sub")
    issuer = claims.get("iss")
    if not isinstance(subject, str) or not subject.strip() or not isinstance(issuer, str) or not issuer.strip():
        return None
    expiry = claims.get("exp")
    if expiry is not None:
        try:
            if float(expiry) <= (time() if now is None else now):
                return None
        except (ValueError, TypeError):
            return None
    return f"{issuer}|{subject}"


def bind_session(state: MutableMapping, subject: str | None) -> None:
    """Discard all private widgets, uploads and results when identity changes."""
    if state.get("_identity") != subject:
        state.clear()
        state["_identity"] = subject


def local_access_enabled(environ: Mapping[str, str]) -> bool:
    # Local use is deliberate and never enabled by a browser/query parameter.
    return environ.get("JOBFORGE_LOCAL_MODE", "").lower() == "true" and not any(
        environ.get(key) for key in ("RAILWAY_ENVIRONMENT_ID", "RAILWAY_PROJECT_ID", "PORT")
    )
