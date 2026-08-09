import hashlib

import rfc8785

from polyglot.platform.json_types import JsonValue


def canonical_json_bytes(payload: JsonValue) -> bytes:
    try:
        return rfc8785.dumps(payload)
    except rfc8785.CanonicalizationError as error:
        raise TypeError("payload is outside the canonical JSON domain") from error


def canonical_json_fingerprint(payload: JsonValue) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
