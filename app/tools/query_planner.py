from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable

from app.schemas.candidate import CandidatePreferences, CandidateProfile


GENERIC_ROLE_TOKENS = {
    "graduate",
    "junior",
    "entry",
    "level",
    "associate",
    "mid",
    "senior",
    "staff",
    "principal",
    "lead",
    "intern",
    "internship",
    "engineer",
    "engineering",
    "developer",
    "specialist",
}


@dataclass(frozen=True)
class RoleFamily:
    canonical: str
    aliases: tuple[str, ...]
    skill_terms: tuple[str, ...] = ()


ROLE_TAXONOMY = (
    RoleFamily(
        "software engineer",
        ("software developer", "backend engineer", "backend developer", "platform engineer", "application engineer"),
        ("python", "java", "typescript", "api"),
    ),
    RoleFamily(
        "machine learning engineer",
        ("ml engineer", "AI engineer", "applied scientist", "MLOps engineer"),
        ("python", "pytorch", "machine learning"),
    ),
    RoleFamily(
        "data analyst",
        ("analytics analyst", "BI analyst", "business intelligence analyst", "data scientist"),
        ("sql", "python", "power bi"),
    ),
    RoleFamily(
        "data engineer",
        ("analytics engineer", "data platform engineer", "ETL developer"),
        ("sql", "python", "spark"),
    ),
    RoleFamily(
        "computer vision engineer",
        ("perception engineer", "vision engineer", "image processing engineer"),
        ("opencv", "pytorch", "c++"),
    ),
    RoleFamily(
        "robotics engineer",
        ("robotics software engineer", "autonomy engineer", "robot perception engineer"),
        ("ros2", "c++", "python"),
    ),
    RoleFamily(
        "full stack engineer",
        ("full-stack developer", "full stack developer", "product engineer"),
        ("typescript", "react", "python"),
    ),
    RoleFamily(
        "security engineer",
        ("cyber security engineer", "security analyst", "application security engineer"),
        ("security", "cloud", "linux"),
    ),
)


@dataclass(frozen=True)
class QueryVariant:
    text: str
    weight: float
    kind: str
    canonical_role: str


@dataclass(frozen=True)
class SearchQueryPlan:
    variants: tuple[QueryVariant, ...]
    rotation_bucket: int = 0

    def for_provider(self, provider: str, limit: int) -> list[str]:
        if limit <= 0:
            return []
        preferred_kinds = {
            "adzuna": ("exact", "alias", "seniority", "skill"),
            "serpapi-multiboard": ("exact", "alias", "seniority", "skill"),
            "serpapi-google-jobs": ("exact", "seniority", "alias", "skill"),
            "remotive": ("exact", "alias", "skill", "seniority"),
            "ats": ("exact", "alias", "skill", "seniority"),
        }.get(provider, ("exact", "alias", "seniority", "skill"))
        kind_order = {kind: index for index, kind in enumerate(preferred_kinds)}
        ranked = sorted(
            self.variants,
            key=lambda item: (kind_order.get(item.kind, 99), -item.weight, item.text.lower()),
        )
        if len(ranked) <= limit:
            return [item.text for item in ranked]
        anchors: list[QueryVariant] = []
        anchored_roles: set[str] = set()
        for item in ranked:
            if item.kind == "exact" and item.canonical_role not in anchored_roles:
                anchors.append(item)
                anchored_roles.add(item.canonical_role)
        anchors = anchors[:limit]
        remaining = [item for item in ranked if item not in anchors]
        offset = _rotation_offset(self.rotation_bucket, provider, len(remaining))
        rotated = remaining[offset:] + remaining[:offset]
        selected = sorted(
            [*anchors, *rotated[: max(0, limit - len(anchors))]],
            key=lambda item: (-item.weight, kind_order.get(item.kind, 99), item.text.lower()),
        )
        return [item.text for item in selected]


def plan_for_preferences(preferences: CandidatePreferences, *, rotation_bucket: int = 0) -> SearchQueryPlan:
    roles = preferences.target_roles or preferences.career_interests or ["software engineer"]
    return _build_plan(
        roles,
        levels=preferences.selected_experience_levels(),
        skills=(),
        rotation_bucket=rotation_bucket,
    )


def plan_for_profile(profile: CandidateProfile, *, rotation_bucket: int = 0) -> SearchQueryPlan:
    roles = profile.target_roles or profile.career_themes or ["software engineer"]
    return _build_plan(
        roles,
        levels=profile.experience_levels or [profile.experience_level],
        skills=sorted(profile.supported_skill_names()),
        rotation_bucket=rotation_bucket,
    )


def role_match_score(requested_role: str, candidate_title: str) -> float:
    requested = normalize_role(requested_role)
    candidate = normalize_role(candidate_title)
    if not requested or not candidate:
        return 0.0
    if requested == candidate or requested in candidate:
        return 1.0

    requested_family = role_family(requested)
    candidate_family = role_family(candidate)
    if requested_family and candidate_family and requested_family.canonical == candidate_family.canonical:
        return 0.9

    requested_tokens = distinctive_role_tokens(requested)
    candidate_tokens = distinctive_role_tokens(candidate)
    if not requested_tokens or not candidate_tokens:
        return 0.0
    coverage = len(requested_tokens & candidate_tokens) / len(requested_tokens)
    occupation_match = bool({"engineer", "developer", "analyst", "scientist"} & set(candidate.split()))
    return round(coverage * (1.0 if occupation_match else 0.8), 4)


def role_matches(requested_role: str, candidate_title: str, *, threshold: float = 0.65) -> bool:
    return role_match_score(requested_role, candidate_title) >= threshold


def role_family(value: str) -> RoleFamily | None:
    normalized = normalize_role(value)
    matches: list[tuple[int, RoleFamily]] = []
    for family in ROLE_TAXONOMY:
        names = (family.canonical, *family.aliases)
        for name in names:
            normalized_name = normalize_role(name)
            if _phrase_matches(normalized, normalized_name):
                matches.append((len(normalized_name.split()), family))
    return max(matches, key=lambda item: item[0])[1] if matches else None


def distinctive_role_tokens(value: str) -> set[str]:
    return {
        _token_alias(token)
        for token in re.findall(r"[a-z0-9+#.]{2,}", normalize_role(value))
        if token not in GENERIC_ROLE_TOKENS
    }


def normalize_role(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+#.]+", " ", value.lower())).strip()


def _build_plan(
    roles: Iterable[str],
    *,
    levels: Iterable[str],
    skills: Iterable[str],
    rotation_bucket: int,
) -> SearchQueryPlan:
    variants: dict[str, QueryVariant] = {}
    selected_levels = [level for level in levels if level][:2]
    selected_skills = [skill for skill in skills if skill][:4]
    for raw_role in roles:
        role = normalize_role(raw_role)
        if not role:
            continue
        family = role_family(role)
        canonical = family.canonical if family else role
        _add_variant(variants, QueryVariant(role, 1.0, "exact", canonical))
        if family:
            for index, alias in enumerate(family.aliases):
                _add_variant(variants, QueryVariant(alias, 0.9 - index * 0.03, "alias", canonical))
        for index, level in enumerate(selected_levels):
            _add_variant(variants, QueryVariant(f"{level} {canonical}", 0.86 - index * 0.03, "seniority", canonical))
        skill_terms = selected_skills or list(family.skill_terms[:3] if family else ())
        if skill_terms:
            _add_variant(
                variants,
                QueryVariant(f"{canonical} {' '.join(skill_terms[:3])}", 0.78, "skill", canonical),
            )
    return SearchQueryPlan(tuple(variants.values()), rotation_bucket=rotation_bucket)


def _add_variant(target: dict[str, QueryVariant], variant: QueryVariant) -> None:
    key = normalize_role(variant.text)
    incumbent = target.get(key)
    if incumbent is None or variant.weight > incumbent.weight:
        target[key] = variant


def _phrase_matches(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?:^|\s){re.escape(phrase)}(?:$|\s)", text))


def _token_alias(token: str) -> str:
    return {
        "analytics": "data",
        "vision": "vision",
        "perception": "vision",
        "ml": "machine",
        "ai": "machine",
        "software": "software",
        "platform": "software",
        "application": "software",
    }.get(token, token)


def _rotation_offset(bucket: int, provider: str, count: int) -> int:
    if count <= 1:
        return 0
    digest = hashlib.sha256(f"{bucket}:{provider}".encode("utf-8")).digest()
    return int.from_bytes(digest[:2], "big") % count
