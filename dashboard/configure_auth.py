"""Materialize Railway's server-only auth setting before Streamlit starts."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit

import toml

AUTH_ENV = "JOBFORGE_AUTH_CONFIG"
ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FIELDS = ("redirect_uri", "cookie_secret", "client_id", "client_secret", "server_metadata_url")


def provision_auth_config(environ, destination: Path) -> bool:
    raw = environ.get(AUTH_ENV)
    if not raw:
        return False
    try:
        config = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("JOBFORGE_AUTH_CONFIG must contain a JSON auth configuration.") from exc
    if not isinstance(config, dict) or any(
        not isinstance(config.get(key), str) or not config[key].strip()
        for key in REQUIRED_FIELDS
    ):
        raise ValueError("The auth configuration is missing required string settings.")
    if len(config["cookie_secret"]) < 32:
        raise ValueError("The auth cookie secret must be at least 32 characters.")
    redirect = urlsplit(config["redirect_uri"])
    metadata = urlsplit(config["server_metadata_url"])
    if not (
        redirect.scheme == "https" or
        (redirect.scheme == "http" and redirect.hostname in {"localhost", "127.0.0.1"})
    ) or not redirect.hostname or redirect.path != "/oauth2callback" or redirect.query or redirect.fragment or redirect.username:
        raise ValueError("The auth callback must use HTTPS, or HTTP on localhost, at /oauth2callback.")
    if metadata.scheme != "https" or not metadata.hostname or metadata.username or metadata.fragment:
        raise ValueError("The identity provider metadata URL must use HTTPS.")
    if "client_kwargs" in config and not isinstance(config["client_kwargs"], dict):
        raise ValueError("Auth client_kwargs must be an object.")
    destination = Path(destination)
    existing = toml.load(destination) if destination.exists() else {}
    existing["auth"] = config
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent, delete=False) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            toml.dump(existing, handle)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True


def main() -> None:
    try:
        provision_auth_config(os.environ, ROOT / ".streamlit/secrets.toml")
    except (ValueError, OSError, toml.TomlDecodeError):
        # Configuration exceptions must never dump environment values or secrets.
        print("JobForge auth configuration is invalid or could not be provisioned. Check the server settings.", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
