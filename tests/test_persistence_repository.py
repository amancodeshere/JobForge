from __future__ import annotations

import pytest

from app.persistence import PersistenceError, SavedJobState, SQLiteUserRepository, UserIdentity


@pytest.fixture()
def repository():
    store = SQLiteUserRepository()
    yield store
    store.close()


@pytest.fixture()
def users(repository):
    alice = repository.upsert_user(UserIdentity(subject="auth0|alice", email="alice@example.test", display_name="Alice"))
    bob = repository.upsert_user(UserIdentity(subject="auth0|bob", email="bob@example.test", display_name="Bob"))
    return alice, bob


def test_private_resources_are_unreadable_across_users(repository, users):
    alice, bob = users
    cv = repository.save_cv_metadata(
        alice.id,
        storage_key=f"users/{alice.id}/cv/alice.pdf",
        original_filename="alice.pdf",
        content_type="application/pdf",
        byte_size=100,
        checksum="sha256:alice",
    )
    preferences_id = repository.save_preferences(alice.id, {"target_roles": ["software engineer"]})
    search = repository.create_search_run(
        alice.id,
        preferences_id=preferences_id,
        input_payload={"target_roles": ["software engineer"]},
        result_payload={"ranked_jobs": [{"job_id": "job-1"}]},
        status="completed",
    )

    with pytest.raises(PersistenceError):
        repository.get_cv_document(bob.id, cv.id)
    with pytest.raises(PersistenceError):
        repository.get_search_run(bob.id, search.id)
    assert repository.get_active_preferences(bob.id) is None
    assert repository.export_user_data(bob.id)["cv_documents"] == []


def test_cv_metadata_requires_private_owner_scoped_key(repository, users):
    alice, _bob = users

    with pytest.raises(PersistenceError, match="scoped to the owner"):
        repository.save_cv_metadata(
            alice.id,
            storage_key="public/alice.pdf",
            original_filename="alice.pdf",
            content_type="application/pdf",
            byte_size=100,
            checksum="sha256:alice",
        )


def test_saved_jobs_and_applications_are_scoped_to_their_owner(repository, users):
    alice, bob = users
    cv = repository.save_cv_metadata(
        alice.id,
        storage_key=f"users/{alice.id}/cv/alice.pdf",
        original_filename="alice.pdf",
        content_type="application/pdf",
        byte_size=100,
        checksum="sha256:alice",
    )
    repository.upsert_job_listing("job-1", "https://jobs.example.test/1", {"title": "Engineer"})
    repository.set_saved_job_state(alice.id, "job-1", SavedJobState.SAVED, "Strong fit")
    application = repository.save_application_metadata(
        alice.id,
        job_id="job-1",
        cv_document_id=cv.id,
        status="ready",
        payload={"cover_letter_key": f"users/{alice.id}/applications/letter.txt"},
    )

    assert repository.list_saved_jobs(alice.id) == [("job-1", SavedJobState.SAVED, "Strong fit")]
    assert repository.list_saved_jobs(bob.id) == []
    with pytest.raises(PersistenceError):
        repository.get_application(bob.id, application.id)
    with pytest.raises(PersistenceError):
        repository.save_application_metadata(
            bob.id,
            job_id="job-1",
            cv_document_id=cv.id,
            status="ready",
            payload={},
        )


def test_user_upsert_keeps_one_internal_identity_and_updates_profile(repository):
    first = repository.upsert_user(UserIdentity(subject="auth0|alice", email="a@example.test", display_name="Alice"))
    second = repository.upsert_user(UserIdentity(subject="auth0|alice", email="alice@example.test", display_name="Alice Example"))

    assert first.id == second.id
    assert second.email == "alice@example.test"
    assert second.display_name == "Alice Example"
