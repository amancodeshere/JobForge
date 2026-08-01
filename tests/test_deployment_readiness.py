from app.evaluation.deployment_readiness import deployment_readiness_checks


def test_deployment_readiness_passes_for_sample_payload():
    checks = deployment_readiness_checks()

    assert all(check.passed for check in checks)


def test_deployment_readiness_requires_latex_engine_in_build_plan(tmp_path):
    from app.evaluation.deployment_readiness import _check_latex_build_config

    config = tmp_path / "nixpacks.toml"
    config.write_text('[phases.setup]\nnixPkgs = ["...", "python"]\n', encoding="utf-8")

    check = _check_latex_build_config(config)

    assert check.passed is False
    assert "Tectonic" in check.issues[0]
