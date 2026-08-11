from pathlib import Path

from polyglot.bootstrap.pilot import fixture_root_from_environment


def test_fixture_root_can_be_pinned_for_reproducible_publication(monkeypatch) -> None:
    monkeypatch.setenv("POLYGLOT_FIXTURES_PATH", "/tmp/polyglot-fixtures")

    assert fixture_root_from_environment() == Path("/tmp/polyglot-fixtures").resolve()
