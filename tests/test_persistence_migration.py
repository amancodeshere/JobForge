from pathlib import Path


MIGRATION = Path("supabase/migrations/202608020001_public_beta_foundation.sql")


def test_public_beta_migration_has_all_owned_records_and_private_bucket():
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    for table in [
        "users", "cv_documents", "candidate_profiles", "search_preferences", "search_runs",
        "job_listings", "saved_jobs", "applications", "feedback", "usage_events",
    ]:
        assert f"public.{table}" in sql
    assert "jobforge-private" in sql
    assert "public = false" in sql


def test_public_beta_migration_enables_row_level_security_for_private_tables():
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    for table in [
        "users", "cv_documents", "candidate_profiles", "search_preferences", "search_runs",
        "saved_jobs", "applications", "feedback", "usage_events",
    ]:
        assert f"alter table public.{table} enable row level security" in sql
    assert "auth.jwt() ->> 'sub'" in sql
    assert "current_jobforge_user_id" in sql
