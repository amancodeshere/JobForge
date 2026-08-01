from app.agents.candidate_profile_agent import CandidateProfileAgent, _guess_section
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
    assert profile.candidate_name == "Aman Sharma"
    assert profile.verified_evidence
    assert all(skill.evidence_ids for skill in profile.skills)
    assert [project.name for project in profile.projects] == [
        "sUNSWim Robotics project",
        "Machine learning project",
        "Full-stack development project",
        "Data analysis project",
        "Robotics software project",
    ]


def test_machine_learning_is_not_misclassified_as_learning():
    profile = CandidateProfileAgent().run(
        "sample_data/cvs/aman_sharma_cv.txt",
        CandidatePreferences(),
    )

    machine_learning = next(skill for skill in profile.skills if skill.name == "Machine Learning")

    assert machine_learning.evidence_type == "inferred_from_project"


def test_project_names_containing_unsw_are_not_misclassified_as_education():
    assert _guess_section("sUNSWim Robotics project: Built an underwater vehicle") == "Projects/Experience"
