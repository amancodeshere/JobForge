from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from dashboard.access import authenticated_subject, bind_session, local_access_enabled
from dashboard.documents import inspect_cv

ROOT = Path(__file__).resolve().parents[1]


def test_identity_requires_verified_login_and_stable_issuer_subject():
    assert authenticated_subject({"sub": "a", "iss": "provider"}) is None
    assert authenticated_subject({"is_logged_in": True, "email": "a@example.com"}) is None
    assert authenticated_subject({"is_logged_in": True, "sub": "a", "iss": "provider", "exp": 20}, now=10) == "provider|a"
    for expiry in (0, 10, "invalid"):
        assert authenticated_subject({"is_logged_in": True, "sub": "a", "iss": "provider", "exp": expiry}, now=10) is None


def test_identity_change_discards_private_uploads_results_and_preferences():
    state = {"_identity": "a", "cv_document": b"private", "search_result": {"private": True}, "roles": "private"}
    bind_session(state, "a")
    assert "cv_document" in state
    bind_session(state, "b")
    assert state == {"_identity": "b"}
    bind_session(state, None)
    assert state == {"_identity": None}


def test_local_access_is_explicit_and_disabled_on_hosted_service():
    assert not local_access_enabled({})
    assert local_access_enabled({"JOBFORGE_LOCAL_MODE": "true"})
    for key in ("RAILWAY_PROJECT_ID", "RAILWAY_ENVIRONMENT_ID", "PORT"):
        assert not local_access_enabled({"JOBFORGE_LOCAL_MODE": "true", key: "set"})


def test_cv_inspection_rejects_empty_large_unsupported_and_unreadable_files():
    for name, content in [("cv.txt", b""), ("cv.exe", b"a" * 100), ("cv.pdf", b"not a PDF"),
                          ("cv.txt", b"a" * (10 * 1024 * 1024 + 1)), ("cv.txt", b"short")]:
        with pytest.raises(ValueError):
            inspect_cv(name, content)
    content = (ROOT / "sample_data/cvs/aman_sharma_cv.txt").read_bytes()
    assert len(inspect_cv("my-cv.txt", content)) > 40


def page_app(name, monkeypatch, *, local=False):
    if local:
        monkeypatch.setenv("JOBFORGE_LOCAL_MODE", "true")
    else:
        monkeypatch.delenv("JOBFORGE_LOCAL_MODE", raising=False)
    for key in ("PORT", "RAILWAY_PROJECT_ID", "RAILWAY_ENVIRONMENT_ID"):
        monkeypatch.delenv(key, raising=False)
    # Callable pages are exercised directly in the same entrypoint context.
    source = (ROOT / "dashboard/streamlit_app.py").read_text()
    source = source.replace('ROOT = Path(__file__).resolve().parents[1]', f'ROOT = Path({str(ROOT)!r})')
    source = source.replace('st.navigation(pages, position="top").run()', f'st.navigation(pages, position="top")\n{name}()')
    app = AppTest.from_string(source, default_timeout=20)
    # Tests must not consume a developer's real identity-provider configuration.
    app.secrets["auth"] = {}
    return app.run()


def test_private_workspace_is_gated_without_authentication(monkeypatch):
    app = page_app("workspace", monkeypatch)
    assert not app.exception
    assert any("identity provider" in item.value for item in app.info)
    assert not app.get("file_uploader")


def test_local_workspace_has_empty_cv_and_preferences_guard(monkeypatch):
    app = page_app("workspace", monkeypatch, local=True)
    assert not app.exception
    assert app.button[0].label == "Continue to preferences"
    assert app.button[0].disabled
    app.segmented_control[0].set_value("Preferences").run()
    assert not app.exception
    assert any("Upload your CV" in item.value for item in app.info)


def test_demo_filter_and_sort_do_not_create_private_results(monkeypatch):
    app = page_app("demo", monkeypatch)
    assert not app.exception
    assert any("demonstration results" in item.value for item in app.info)
    app.text_input[0].set_value("no-such-company-xyz").run()
    assert not app.exception
    assert any("No roles match" in item.value for item in app.info)
    assert "search_result" not in app.session_state
    app.text_input[0].set_value("").run()
    app.selectbox[0].set_value("Company A–Z").run()
    assert not app.exception


def test_continue_and_successful_search_reach_results_without_losing_cv(monkeypatch):
    from types import SimpleNamespace
    from app.agents.orchestrator_agent import OrchestratorAgent
    import dashboard.results

    calls = []

    def search(_self, **kwargs):
        assert Path(kwargs["cv_path"]).read_text() == "CV evidence for the test candidate"
        assert kwargs["use_live_search"] is True
        assert kwargs["sample_fallback"] is False
        calls.append(kwargs["preferences"])
        return SimpleNamespace(candidate_profile=SimpleNamespace(candidate_name="Test candidate"))

    monkeypatch.setattr(OrchestratorAgent, "search", search)
    monkeypatch.setattr(dashboard.results, "render_results", lambda *_a, **_k: None)
    app = page_app("workspace", monkeypatch, local=True)
    app.session_state["cv_document"] = dict(name="cv.txt", content=b"CV evidence for the test candidate", text="CV evidence for the test candidate", digest="test")
    app.run()
    next(button for button in app.button if button.label == "Continue to preferences").click().run()
    assert not app.exception
    assert app.segmented_control[0].value == "Preferences"
    app.text_area[0].set_value("Data analyst")
    app.text_input(key="locations").set_value("Sydney")
    app.multiselect(key="levels").set_value(["junior"])
    app.text_input(key="work_rights").set_value("Australian unrestricted work rights")
    next(button for button in app.button if button.label == "Find matching jobs").click().run()
    assert not app.exception
    assert app.segmented_control[0].value == "Results"
    assert calls[0].target_roles == ["Data analyst"]
    assert app.session_state["cv_document"]["name"] == "cv.txt"
    app.segmented_control[0].set_value("Preferences").run()
    assert app.text_area[0].value == "Data analyst"


def test_configured_provider_offers_login_and_keeps_workspace_private(monkeypatch):
    app = page_app("workspace", monkeypatch)
    app.secrets["auth"] = dict(redirect_uri="http://localhost:8501/oauth2callback",
                               cookie_secret="test-cookie-secret-for-isolated-ui-tests",
                               client_id="test-client", client_secret="test-secret",
                               server_metadata_url="https://tenant.example/.well-known/openid-configuration")
    app.run()
    assert not app.exception
    assert any(button.label == "Continue to secure sign-in" for button in app.button)
    assert not app.get("file_uploader")
