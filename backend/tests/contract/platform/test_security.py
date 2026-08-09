from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_tracked_repository_and_history_have_no_high_confidence_secrets() -> None:
    from polyglot.platform.security_checks import scan_git_repository

    findings = scan_git_repository(ROOT)

    assert findings == []


def test_fx_ops_is_a_synthetic_platform_only_fixture() -> None:
    import json

    fixture = Path(__file__).parents[2] / "integration/platform/fixtures/FX-OPS"
    manifest = json.loads((fixture / "manifest.json").read_text())
    seed = json.loads((fixture / "platform-seed.json").read_text())

    assert manifest == {
        "fixture_code": "FX-OPS",
        "schema_version": 1,
        "synthetic": True,
        "business_records": 0,
        "scenarios": [
            "blocked_outbox",
            "expired_job_claim",
            "deletion_tombstone",
            "version_n_minus_1",
        ],
    }
    assert seed["fixture_code"] == "FX-OPS"
    assert seed["business_data"] == []
    assert set(seed["platform_state"]) == {
        "blocked_outbox",
        "expired_job_claim",
        "deletion_tombstone",
        "version_n_minus_1",
    }
