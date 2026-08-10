from __future__ import annotations

import io
import stat
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

from polyglot.platform.errors import DomainError, ErrorCode


@dataclass(frozen=True, slots=True)
class ImportLimits:
    max_archive_bytes: int = 10 * 1024 * 1024
    max_entries: int = 100
    max_entry_bytes: int = 10 * 1024 * 1024
    max_uncompressed_bytes: int = 50 * 1024 * 1024
    max_compression_ratio: int = 100


@dataclass(frozen=True, slots=True)
class ArchiveEntry:
    path: str
    compressed_size: int
    uncompressed_size: int
    crc32: int


@dataclass(frozen=True, slots=True)
class ArchiveInspection:
    entries: tuple[ArchiveEntry, ...]
    compressed_size: int
    uncompressed_size: int


def _safe_path(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts


def inspect_zip(payload: bytes, limits: ImportLimits) -> ArchiveInspection:
    if len(payload) > limits.max_archive_bytes:
        raise DomainError(ErrorCode.SIZE_LIMIT_EXCEEDED)
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
        entries = archive.infolist()
    except (OSError, zipfile.BadZipFile) as error:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid zip archive") from error
    if len(entries) > limits.max_entries:
        raise DomainError(ErrorCode.SIZE_LIMIT_EXCEEDED)
    inspected: list[ArchiveEntry] = []
    total_uncompressed = 0
    for entry in entries:
        mode = entry.external_attr >> 16
        ratio = entry.file_size / max(entry.compress_size, 1)
        if (
            not _safe_path(entry.filename)
            or stat.S_ISLNK(mode)
            or entry.flag_bits & 0x1
        ):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="unsafe zip entry")
        if (
            entry.file_size > limits.max_entry_bytes
            or ratio > limits.max_compression_ratio
        ):
            raise DomainError(ErrorCode.SIZE_LIMIT_EXCEEDED)
        total_uncompressed += entry.file_size
        if total_uncompressed > limits.max_uncompressed_bytes:
            raise DomainError(ErrorCode.SIZE_LIMIT_EXCEEDED)
        inspected.append(
            ArchiveEntry(
                path=entry.filename,
                compressed_size=entry.compress_size,
                uncompressed_size=entry.file_size,
                crc32=entry.CRC,
            )
        )
    return ArchiveInspection(tuple(inspected), len(payload), total_uncompressed)


def read_single_safe_zip_entry(payload: bytes, limits: ImportLimits) -> bytes:
    inspection = inspect_zip(payload, limits)
    if len(inspection.entries) != 1:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="one import file is required")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        result = archive.read(inspection.entries[0].path)
    if len(result) != inspection.entries[0].uncompressed_size:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="zip entry size changed")
    return result
