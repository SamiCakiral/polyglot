from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
POSTGRES_IMAGE = (
    "postgres:17-alpine@sha256:"
    "742f40ea20b9ff2ff31db5458d127452988a2164df9e17441e191f3b72252193"
)


def test_ci_gates_migration_round_trip_drift_and_installed_wheel() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()

    downgrade = workflow.index("uv run alembic downgrade base")
    upgrade = workflow.index("uv run alembic upgrade head", downgrade)
    drift = workflow.index("uv run alembic check", upgrade)
    assert downgrade < upgrade < drift
    assert "test_installed_artifact.py" in workflow


def test_ci_prepares_dependency_image_and_repository_security_gates() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()

    assert "uv export --frozen --no-dev" in workflow
    assert "pip-audit" in workflow
    assert "--disable-pip --require-hashes -r" in workflow
    assert "aquasecurity/trivy-action" in workflow
    assert "polyglot.platform.security_checks" in workflow


def test_ci_uses_the_compose_postgres_digest_for_service_and_scan() -> None:
    compose = (ROOT / "compose.yaml").read_text()
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()

    assert f"image: {POSTGRES_IMAGE}" in compose
    assert workflow.count(f"image: {POSTGRES_IMAGE}") == 1
    assert workflow.count(f"image-ref: {POSTGRES_IMAGE}") == 1
