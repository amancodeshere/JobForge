import json
import stat

import pytest
import toml

from dashboard.configure_auth import provision_auth_config


def configuration():
    return dict(redirect_uri="https://jobs.example/oauth2callback", cookie_secret="test-cookie-secret-" * 3,
                client_id="test-client", client_secret="test-client-secret",
                server_metadata_url="https://tenant.example/.well-known/openid-configuration",
                client_kwargs={"prompt": "login", "token_endpoint_auth_method": "client_secret_post"})


def test_absent_environment_preserves_existing_local_secrets(tmp_path):
    path = tmp_path / "secrets.toml"
    path.write_text('[other]\nvalue = "keep"\n')
    assert not provision_auth_config({}, path)
    assert toml.load(path) == {"other": {"value": "keep"}}


def test_provision_auth_preserves_other_settings_and_restricts_permissions(tmp_path):
    path = tmp_path / "secrets.toml"
    path.write_text('[other]\nvalue = "keep"\n')
    config = configuration()
    assert provision_auth_config({"JOBFORGE_AUTH_CONFIG": json.dumps(config)}, path)
    assert toml.load(path) == {"other": {"value": "keep"}, "auth": config}
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("change", [
    {"redirect_uri": "http://jobs.example/oauth2callback"},
    {"redirect_uri": "https://jobs.example/wrong"},
    {"redirect_uri": "https://user:password@jobs.example/oauth2callback"},
    {"server_metadata_url": "http://tenant.example/metadata"},
    {"cookie_secret": "short"}, {"client_secret": ""}, {"client_kwargs": "invalid"},
])
def test_invalid_configuration_does_not_replace_existing_secrets(tmp_path, change):
    path = tmp_path / "secrets.toml"
    path.write_text('[other]\nvalue = "keep"\n')
    config = configuration() | change
    with pytest.raises(ValueError):
        provision_auth_config({"JOBFORGE_AUTH_CONFIG": json.dumps(config)}, path)
    assert toml.load(path) == {"other": {"value": "keep"}}


def test_malformed_json_does_not_expose_value(tmp_path):
    with pytest.raises(ValueError) as error:
        provision_auth_config({"JOBFORGE_AUTH_CONFIG": "secret-not-json"}, tmp_path / "secrets.toml")
    assert "secret-not-json" not in str(error.value)
