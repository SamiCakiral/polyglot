import hashlib
import json

from polyglot.platform.json_types import JsonValue


def canonical_json_bytes(payload: JsonValue) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_json_fingerprint(payload: JsonValue) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
