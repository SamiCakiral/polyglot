from __future__ import annotations

import io
import stat
import zipfile

import pytest

from polyglot.modules.lexicon.exchange.security import (
    ImportLimits,
    inspect_zip,
    read_single_safe_zip_entry,
)
from polyglot.platform.errors import DomainError, ErrorCode


def archive(entries: tuple[tuple[str, bytes, int | None], ...]) -> bytes:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as output:
        for name, content, mode in entries:
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_DEFLATED
            if mode is not None:
                info.create_system = 3
                info.external_attr = mode << 16
            output.writestr(info, content)
    return target.getvalue()


def test_normative_import_limits_are_locked() -> None:
    assert ImportLimits() == ImportLimits(
        max_archive_bytes=50 * 1024 * 1024,
        max_entries=1_000,
        max_entry_bytes=20 * 1024 * 1024,
        max_uncompressed_bytes=200 * 1024 * 1024,
        max_compression_ratio=20,
        max_path_length=512,
    )


@pytest.mark.parametrize(
    "entries",
    (
        (("../payload.json", b"{}", None),),
        (("folder\\payload.json", b"{}", None),),
        (("payload.json", b"{}", stat.S_IFREG | 0o755),),
        (("payload.json", b"{}", stat.S_IFLNK | 0o777),),
        (("café.json", b"{}", None), ("cafe\u0301.json", b"{}", None)),
    ),
)
def test_archive_rejects_ambiguous_or_dangerous_entries(entries) -> None:
    with pytest.raises(DomainError) as rejected:
        inspect_zip(archive(entries), ImportLimits())
    assert rejected.value.code is ErrorCode.VALIDATION_FAILED


def test_archive_rejects_ratio_entry_count_and_total_size() -> None:
    compressed = archive((("payload.json", b"a" * 1_000, None),))
    with pytest.raises(DomainError) as ratio:
        inspect_zip(compressed, ImportLimits(max_compression_ratio=1))
    with pytest.raises(DomainError) as entries:
        inspect_zip(
            archive((("one.json", b"{}", None), ("two.json", b"{}", None))),
            ImportLimits(max_entries=1),
        )
    with pytest.raises(DomainError) as total:
        inspect_zip(compressed, ImportLimits(max_uncompressed_bytes=999))
    assert {ratio.value.code, entries.value.code, total.value.code} == {
        ErrorCode.SIZE_LIMIT_EXCEEDED
    }


def test_single_entry_rejects_nested_binary_and_wrong_declared_type() -> None:
    nested = archive((("nested.zip", b"PK\x03\x04payload", None),))
    binary = archive((("payload.json", b"{}\x00", None),))
    wrong_type = archive((("payload.csv", b"question,answer", None),))

    for payload, format_id in (
        (nested, "polyglot.lexicon.bundle/v1"),
        (binary, "polyglot.lexicon.bundle/v1"),
        (wrong_type, "polyglot.lexicon.bundle/v1"),
    ):
        with pytest.raises(DomainError) as rejected:
            read_single_safe_zip_entry(payload, ImportLimits(), format_id=format_id)
        assert rejected.value.code is ErrorCode.VALIDATION_FAILED


def test_single_entry_accepts_json_and_qa_csv() -> None:
    json_payload = archive((("payload.json", b"{}", None),))
    csv_payload = archive((("payload.csv", b"question,answer,variety_id\nq,a,v", None),))

    assert (
        read_single_safe_zip_entry(
            json_payload,
            ImportLimits(),
            format_id="polyglot.lexicon.bundle/v1",
        )
        == b"{}"
    )
    assert read_single_safe_zip_entry(
        csv_payload,
        ImportLimits(),
        format_id="polyglot.generic.qa/v1",
    ).startswith(b"question")
