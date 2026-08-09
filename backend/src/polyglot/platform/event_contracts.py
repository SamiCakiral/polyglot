import json
from functools import lru_cache
from pathlib import Path


def _contract_path(name: str) -> Path:
    packaged = Path(__file__).with_name("contracts") / name
    if packaged.is_file():
        return packaged
    repository_contract = Path(__file__).resolve().parents[4] / "contracts/events" / name
    if repository_contract.is_file():
        return repository_contract
    raise RuntimeError(f"packaged event contract is missing: {name}")


@lru_cache(maxsize=1)
def canonical_event_versions() -> frozenset[tuple[str, int]]:
    document = json.loads(_contract_path("event-catalogue.yaml").read_text())
    return frozenset(
        (event["event_type"], event["schema_version"])
        for event in document["events"]
    )
