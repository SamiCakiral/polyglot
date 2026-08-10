import hashlib
import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[4] / "fixtures/canonical/FX-SPRINTS"


def test_sprint_fixture_declares_all_budgets_and_offline_oracles() -> None:
    payload = json.loads((FIXTURE / "sprints.json").read_text())
    metadata = json.loads((FIXTURE / "fixture-metadata.json").read_text())

    assert payload["budgets"] == list(range(10, 61, 5))
    assert payload["required_roles"] == ["activation", "primary_objective", "reflection"]
    assert payload["delayed_recode"]["duplicate_on_late_resume"] is False
    assert payload["free_practice"]["consumes_module_day"] is False
    assert metadata["network_dependencies"] == []
    digest = hashlib.sha256((FIXTURE / "sprints.json").read_bytes()).hexdigest()
    assert metadata["payloads"]["sprints.json"] == f"sha256:{digest}"
