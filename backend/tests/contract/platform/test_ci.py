import re
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
POSTGRES_IMAGE = (
    "postgres:17-alpine@sha256:"
    "742f40ea20b9ff2ff31db5458d127452988a2164df9e17441e191f3b72252193"
)
TRIVY_ACTION_SHA = "ed142fd0673e97e23eac54620cfb913e5ce36c25"
TRIVY_ACTION_RELEASE = "v0.36.0"
TRIVY_BINARY_VERSION = "v0.69.3"


def validate_trivy_pins(workflow: str) -> None:
    action_lines = re.findall(
        r"uses: aquasecurity/trivy-action@([^\s#]+)(?:\s+#\s+(v\d+\.\d+\.\d+))?",
        workflow,
    )
    if len(action_lines) != 2:
        raise ValueError("exactly two Trivy action steps are required")
    for reference, release in action_lines:
        if not re.fullmatch(r"[0-9a-f]{40}", reference):
            raise ValueError("Trivy action must use a full immutable commit SHA")
        if reference != TRIVY_ACTION_SHA or release != TRIVY_ACTION_RELEASE:
            raise ValueError("Trivy action must resolve to the reviewed safe release")
        if tuple(map(int, release.removeprefix("v").split("."))) < (0, 35, 0):
            raise ValueError("pre-0.35 Trivy action releases are forbidden")
    lines = workflow.splitlines()
    versions: list[str] = []
    for index, line in enumerate(lines):
        if "uses: aquasecurity/trivy-action@" not in line:
            continue
        uses_indent = len(line) - len(line.lstrip())
        for following in lines[index + 1 :]:
            stripped = following.strip()
            indent = len(following) - len(following.lstrip())
            if (stripped.startswith("- ") and indent < uses_indent) or (
                stripped.startswith("uses:") and indent <= uses_indent
            ):
                break
            if stripped.startswith("version:"):
                versions.append(stripped.split(":", 1)[1].strip())
                break
    if versions != [TRIVY_BINARY_VERSION, TRIVY_BINARY_VERSION]:
        raise ValueError("each Trivy step must pin the reviewed binary version")


def test_ci_gates_migration_round_trip_drift_and_installed_wheel() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()

    downgrade = workflow.index("uv run alembic downgrade base")
    upgrade = workflow.index("uv run alembic upgrade head", downgrade)
    drift = workflow.index("uv run alembic check", upgrade)
    assert downgrade < upgrade < drift
    assert "POLYGLOT_ALLOW_DESTRUCTIVE_IDENTITY_DOWNGRADE: true" in workflow
    assert "test_installed_artifact.py" in workflow


def test_ci_prepares_dependency_image_and_repository_security_gates() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()

    assert "uv export --frozen --no-dev" in workflow
    assert "pip-audit" in workflow
    assert "--disable-pip --require-hashes -r" in workflow
    assert "aquasecurity/trivy-action" in workflow
    assert "polyglot.platform.security_checks" in workflow
    validate_trivy_pins(workflow)


def test_ci_uses_the_compose_postgres_digest_for_service_and_scan() -> None:
    compose = (ROOT / "compose.yaml").read_text()
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()

    assert f"image: {POSTGRES_IMAGE}" in compose
    assert workflow.count(f"image: {POSTGRES_IMAGE}") == 1
    assert workflow.count(f"image-ref: {POSTGRES_IMAGE}") == 1


def test_ci_bootstraps_then_uses_distinct_non_superuser_database_logins() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()

    bootstrap = workflow.index("Provision PostgreSQL identities")
    migration = workflow.index("uv run alembic upgrade head")
    assert bootstrap < migration
    assert "POSTGRES_USER: polyglot_bootstrap" in workflow
    assert workflow.count("POLYGLOT_BOOTSTRAP_DATABASE_URL:") == 1
    assert (
        "POLYGLOT_MIGRATION_DATABASE_URL: "
        "postgresql+asyncpg://polyglot_migration_login:ci-migration-only@"
        "127.0.0.1:5432/polyglot"
    ) in workflow
    assert (
        "POLYGLOT_DATABASE_URL: "
        "postgresql+asyncpg://polyglot_runtime_login:ci-runtime-only@"
        "127.0.0.1:5432/polyglot"
    ) in workflow
    assert (
        "POLYGLOT_RETENTION_DATABASE_URL: "
        "postgresql+asyncpg://polyglot_retention_login:ci-retention-only@"
        "127.0.0.1:5432/polyglot"
    ) in workflow
    assert "POLYGLOT_TEST_DATABASE_URL" not in workflow


@pytest.mark.parametrize(
    "mutation",
    [
        lambda workflow: workflow.replace(f"@{TRIVY_ACTION_SHA}", "@v0.36.0"),
        lambda workflow: workflow.replace(
            f"@{TRIVY_ACTION_SHA} # {TRIVY_ACTION_RELEASE}", "@0.33.1 # v0.33.1"
        ),
        lambda workflow: workflow.replace(
            f"version: {TRIVY_BINARY_VERSION}", "version: latest", 1
        ),
        lambda workflow: workflow.replace(f"version: {TRIVY_BINARY_VERSION}\n", "", 1),
    ],
)
def test_ci_contract_rejects_mutable_affected_or_unpinned_trivy(
    mutation: Callable[[str], str],
) -> None:
    safe_workflow = "\n".join(
        [
            "      - name: First scan",
            f"        uses: aquasecurity/trivy-action@{TRIVY_ACTION_SHA} # {TRIVY_ACTION_RELEASE}",
            "        with:",
            f"          version: {TRIVY_BINARY_VERSION}",
            "      - name: Second scan",
            f"        uses: aquasecurity/trivy-action@{TRIVY_ACTION_SHA} # {TRIVY_ACTION_RELEASE}",
            "        with:",
            f"          version: {TRIVY_BINARY_VERSION}",
        ]
    )

    with pytest.raises(ValueError):
        validate_trivy_pins(mutation(safe_workflow))
