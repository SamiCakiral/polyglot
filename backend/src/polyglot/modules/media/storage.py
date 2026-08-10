from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from polyglot.modules.media.ports import ObjectStoragePort


@dataclass(slots=True)
class FilesystemObjectStorage(ObjectStoragePort):
    root: Path

    def __post_init__(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, object_key: str) -> Path:
        if not object_key.startswith("media/") or ".." in object_key:
            raise ValueError("invalid private object key")
        path = self.root / object_key
        if self.root.resolve() not in path.resolve().parents:
            raise ValueError("invalid private object key")
        return path

    def write_private(self, object_key: str, content: bytes) -> None:
        path = self._path(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".partial")
        temporary.write_bytes(content)
        temporary.replace(path)

    def read_private(self, object_key: str) -> bytes | None:
        path = self._path(object_key)
        return path.read_bytes() if path.is_file() else None

    def delete_private(self, object_key: str) -> None:
        self._path(object_key).unlink(missing_ok=True)

    def list_private(self, prefix: str) -> tuple[str, ...]:
        if not prefix.startswith("media/") or ".." in prefix:
            raise ValueError("invalid private prefix")
        media_root = self.root / "media"
        if not media_root.exists():
            return ()
        return tuple(
            sorted(
                str(path.relative_to(self.root))
                for path in media_root.rglob("*")
                if path.is_file() and str(path.relative_to(self.root)).startswith(prefix)
            )
        )


@dataclass(frozen=True, slots=True)
class SignedObjectGrant:
    method: str
    resource_id: str
    object_key: str
    expires_at: datetime
    max_bytes: int


class LocalSignedUrlSigner:
    def __init__(self, secret: bytes) -> None:
        if len(secret) < 32:
            raise ValueError("media signing secret must contain at least 32 bytes")
        self._secret = secret

    def issue(self, grant: SignedObjectGrant) -> str:
        payload = "\n".join(
            (
                grant.method,
                grant.resource_id,
                grant.object_key,
                str(int(grant.expires_at.timestamp())),
                str(grant.max_bytes),
            )
        ).encode()
        signature = hmac.new(self._secret, payload, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(payload + b"\n" + signature).rstrip(b"=").decode()

    def verify(
        self, token: str, *, method: str, resource_id: str, now: datetime
    ) -> SignedObjectGrant:
        try:
            padded = token + "=" * (-len(token) % 4)
            decoded = base64.urlsafe_b64decode(padded.encode())
            payload, signature = decoded.rsplit(b"\n", 1)
            expected = hmac.new(self._secret, payload, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError
            raw_method, raw_resource_id, object_key, expires_raw, max_bytes_raw = (
                payload.decode().split("\n")
            )
            grant = SignedObjectGrant(
                method=raw_method,
                resource_id=raw_resource_id,
                object_key=object_key,
                expires_at=datetime.fromtimestamp(int(expires_raw), UTC),
                max_bytes=int(max_bytes_raw),
            )
        except (ValueError, UnicodeError) as error:
            raise ValueError("invalid signed media token") from error
        if grant.method != method or grant.resource_id != resource_id or now >= grant.expires_at:
            raise ValueError("expired or mismatched signed media token")
        return grant
