from __future__ import annotations

import io
import stat
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

from polyglot.platform.errors import DomainError, ErrorCode


@dataclass(frozen=True, slots=True)
class ImportLimits:
    max_archive_bytes: int = 50 * 1024 * 1024
    max_entries: int = 1_000
    max_entry_bytes: int = 20 * 1024 * 1024
    max_uncompressed_bytes: int = 200 * 1024 * 1024
    max_compression_ratio: int = 20
    max_path_length: int = 512


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
    path = PurePosixPath(name.replace("\\", "/"))
    return (
        bool(name)
        and "\x00" not in name
        and "\\" not in name
        and not path.is_absolute()
        and ".." not in path.parts
        and all(part not in {"", "."} for part in path.parts)
    )


def _normalized_path(name: str) -> str:
    return unicodedata.normalize("NFKC", name).casefold()


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
    normalized_paths: set[str] = set()
    total_uncompressed = 0
    for entry in entries:
        mode = entry.external_attr >> 16
        file_type = stat.S_IFMT(mode)
        ratio = entry.file_size / max(entry.compress_size, 1)
        normalized_path = _normalized_path(entry.filename)
        if (
            not _safe_path(entry.filename)
            or stat.S_ISLNK(mode)
            or entry.flag_bits & 0x1
            or entry.is_dir()
            or len(entry.filename) > limits.max_path_length
            or normalized_path in normalized_paths
            or (file_type and not stat.S_ISREG(mode))
            or mode & 0o111
        ):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="unsafe zip entry")
        if entry.file_size > limits.max_entry_bytes or ratio > limits.max_compression_ratio:
            raise DomainError(ErrorCode.SIZE_LIMIT_EXCEEDED)
        total_uncompressed += entry.file_size
        if total_uncompressed > limits.max_uncompressed_bytes:
            raise DomainError(ErrorCode.SIZE_LIMIT_EXCEEDED)
        normalized_paths.add(normalized_path)
        inspected.append(
            ArchiveEntry(
                path=entry.filename,
                compressed_size=entry.compress_size,
                uncompressed_size=entry.file_size,
                crc32=entry.CRC,
            )
        )
    return ArchiveInspection(tuple(inspected), len(payload), total_uncompressed)


def read_single_safe_zip_entry(
    payload: bytes,
    limits: ImportLimits,
    *,
    format_id: str | None = None,
) -> bytes:
    inspection = inspect_zip(payload, limits)
    if len(inspection.entries) != 1:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="one import file is required")
    entry = inspection.entries[0]
    suffix = PurePosixPath(entry.path).suffix.casefold()
    if suffix in {".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar"}:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="nested archives are forbidden")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        try:
            result = archive.read(entry.path)
        except (OSError, RuntimeError, zipfile.BadZipFile) as error:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid zip entry") from error
    if len(result) != entry.uncompressed_size:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="zip entry size changed")
    if result.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="nested archives are forbidden")
    if b"\x00" in result:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="binary import is forbidden")
    if format_id == "polyglot.generic.qa/v1":
        if suffix not in {".csv", ".json"}:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="unexpected import file type")
    elif format_id is not None and suffix != ".json":
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="unexpected import file type")
    return result
