from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


ATSProvider = Literal["greenhouse", "lever", "ashby", "workday"]
ATSMode = Literal["public_api", "indexed_only"]
DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "config" / "ats_boards.json"


class ATSBoardEntry(BaseModel):
    company: str
    provider: ATSProvider
    token: str
    mode: ATSMode
    enabled_by_default: bool = False
    verified_on: date
    verification_url: str
    locations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def public_api_support(self) -> "ATSBoardEntry":
        if self.provider == "workday" and self.mode != "indexed_only":
            raise ValueError("Workday boards must remain indexed-only without an approved public job-board API.")
        if self.provider in {"greenhouse", "lever", "ashby"} and self.mode != "public_api":
            raise ValueError(f"{self.provider} registry entries must use their documented public API.")
        return self


def load_ats_registry(path: str | Path = DEFAULT_REGISTRY_PATH) -> tuple[ATSBoardEntry, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = tuple(ATSBoardEntry.model_validate(item) for item in payload)
    identities = {(entry.provider, entry.token.lower()) for entry in entries}
    if len(identities) != len(entries):
        raise ValueError("ATS registry contains duplicate provider tokens.")
    return entries


def default_public_boards(provider: ATSProvider) -> tuple[ATSBoardEntry, ...]:
    return tuple(
        entry
        for entry in load_ats_registry()
        if entry.provider == provider and entry.mode == "public_api" and entry.enabled_by_default
    )


def indexed_workday_scopes() -> tuple[str, ...]:
    return tuple(
        entry.token
        for entry in load_ats_registry()
        if entry.provider == "workday" and entry.mode == "indexed_only" and entry.enabled_by_default
    )
