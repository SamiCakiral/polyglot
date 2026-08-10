from __future__ import annotations

import io
import zipfile

import pytest

from polyglot.modules.lexicon.exchange.security import ImportLimits, inspect_zip
from polyglot.platform.errors import DomainError, ErrorCode


def _archive(entries: dict[str, bytes], *, declared_size: int | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_DEFLATED
            if declared_size is not None:
                info.file_size = declared_size
            archive.writestr(info, payload)
    return buffer.getvalue()


@pytest.mark.parametrize("name", ("../secret", "/absolute", "a/../../escape"))
def test_archive_inspection_rejects_path_traversal_without_extracting(name: str) -> None:
    with pytest.raises(DomainError) as caught:
        inspect_zip(_archive({name: b"hostile"}), ImportLimits())

    assert caught.value.code is ErrorCode.VALIDATION_FAILED


def test_archive_inspection_rejects_excessive_compression_ratio() -> None:
    payload = b"0" * 200_000
    with pytest.raises(DomainError) as caught:
        inspect_zip(
            _archive({"bundle.json": payload}),
            ImportLimits(max_compression_ratio=5),
        )

    assert caught.value.code is ErrorCode.SIZE_LIMIT_EXCEEDED


def test_archive_inspection_returns_bounded_metadata_only() -> None:
    result = inspect_zip(
        _archive({"bundle.json": b'{"format":"polyglot.lexicon.bundle/v1"}'}),
        ImportLimits(),
    )

    assert result.entries[0].path == "bundle.json"
    assert result.entries[0].uncompressed_size == 39
    assert not hasattr(result.entries[0], "payload")
