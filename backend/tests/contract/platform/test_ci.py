from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_ci_gates_migration_round_trip_drift_and_installed_wheel() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()

    downgrade = workflow.index("uv run alembic downgrade base")
    upgrade = workflow.index("uv run alembic upgrade head", downgrade)
    drift = workflow.index("uv run alembic check", upgrade)
    assert downgrade < upgrade < drift
    assert "test_installed_artifact.py" in workflow


def test_ci_prepares_dependency_image_and_repository_security_gates() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()

    assert "pip-audit" in workflow
    assert "aquasecurity/trivy-action" in workflow
    assert "polyglot.platform.security_checks" in workflow
