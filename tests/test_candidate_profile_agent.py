from app.agents.candidate_profile_agent import CandidateProfileAgent
from app.schemas.candidate import CandidatePreferences


def test_candidate_profile_extracts_skills_with_evidence():
    profile = CandidateProfileAgent().run(
        "sample_data/cvs/aman_sharma_cv.txt",
        CandidatePreferences(),
    )

    skill_names = profile.supported_skill_names()

    assert "python" in skill_names
    assert "pytorch" in skill_names
    assert "opencv" in skill_names
    assert profile.verified_evidence
    assert all(skill.evidence_ids for skill in profile.skills)

