from app.evaluation.deployment_readiness import deployment_readiness_checks


def test_deployment_readiness_passes_for_sample_payload():
    checks = deployment_readiness_checks()

    assert all(check.passed for check in checks)

