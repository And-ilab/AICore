"""Unpack ZIP/RAR OCR batches (FR-OCR-06, IV.3 queue)."""

from __future__ import annotations

import io
import os
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable

from django.conf import settings

DOCUMENT_EXTENSIONS = frozenset(
    {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"}
)
ARCHIVE_EXTENSIONS = frozenset({".zip", ".rar"})
SKIP_NAMES = frozenset({".ds_store", "thumbs.db", "desktop.ini"})

CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}


class ArchiveError(ValueError):
    """Invalid or empty document archive."""


@dataclass(frozen=True)
class ArchiveMember:
    filename: str
    data: bytes
    content_type: str


def is_archive_filename(filename: str) -> bool:
    return PurePosixPath(filename.replace("\\", "/")).suffix.casefold() in ARCHIVE_EXTENSIONS


def _safe_basename(name: str) -> str | None:
    raw = name.replace("\\", "/").strip()
    if not raw or raw.endswith("/"):
        return None
    if raw.startswith("/") or raw.startswith("../") or "/../" in f"/{raw}/":
        return None
    if len(raw) >= 2 and raw[1] == ":":
        return None
    parts = [part for part in PurePosixPath(raw).parts if part not in {".", ""}]
    if ".." in parts:
        return None
    base = PurePosixPath(raw).name
    if not base or base in {".", ".."}:
        return None
    if base.startswith("._"):
        return None
    if base.casefold() in SKIP_NAMES:
        return None
    if any(part.casefold() == "__macosx" for part in parts):
        return None
    return base[:240]


def _limits() -> tuple[int, int, int]:
    max_files = int(getattr(settings, "OCR_ARCHIVE_MAX_FILES", 40))
    max_member = int(
        getattr(settings, "OCR_MAX_UPLOAD_BYTES", 25 * 1024 * 1024)
    )
    max_total = int(getattr(settings, "OCR_ARCHIVE_MAX_TOTAL_BYTES", 80 * 1024 * 1024))
    return max_files, max_member, max_total


def _accept_member(name: str, data: bytes, seen: set[str]) -> ArchiveMember | None:
    safe = _safe_basename(name)
    if not safe:
        return None
    suffix = PurePosixPath(safe).suffix.casefold()
    if suffix not in DOCUMENT_EXTENSIONS:
        return None
    if not data:
        return None
    unique = safe
    index = 2
    stem = PurePosixPath(safe).stem
    while unique.casefold() in seen:
        unique = f"{stem}_{index}{suffix}"
        index += 1
    seen.add(unique.casefold())
    return ArchiveMember(
        filename=unique,
        data=data,
        content_type=CONTENT_TYPES[suffix],
    )


def _extract_zip(raw: bytes) -> list[ArchiveMember]:
    max_files, max_member, max_total = _limits()
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ArchiveError("file is not a valid ZIP archive") from exc

    members: list[ArchiveMember] = []
    seen: set[str] = set()
    total = 0
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            if info.file_size > max_member:
                raise ArchiveError(
                    f"{info.filename} exceeds max size of {max_member} bytes"
                )
            try:
                data = archive.read(info)
            except RuntimeError as exc:
                raise ArchiveError(f"cannot read {info.filename}: {exc}") from exc
            total += len(data)
            if total > max_total:
                raise ArchiveError(f"archive exceeds max unpacked size of {max_total} bytes")
            item = _accept_member(info.filename, data, seen)
            if item is None:
                continue
            members.append(item)
            if len(members) > max_files:
                raise ArchiveError(f"archive has more than {max_files} documents")
    return members


def _configure_rarfile() -> None:
    import rarfile  # type: ignore

    for tool in (
        os.environ.get("OCR_UNRAR_TOOL"),
        "unrar",
        "unrar-free",
        "unar",
        "bsdtar",
    ):
        if tool and shutil.which(tool):
            rarfile.UNRAR_TOOL = tool
            return


def _extract_rar(raw: bytes) -> list[ArchiveMember]:
    try:
        import rarfile  # type: ignore
    except ImportError as exc:
        raise ArchiveError("RAR support is not installed (package rarfile)") from exc

    _configure_rarfile()
    max_files, max_member, max_total = _limits()
    try:
        archive = rarfile.RarFile(io.BytesIO(raw))
    except Exception as exc:  # rarfile.Error and missing tool
        raise ArchiveError(f"cannot open RAR archive: {exc}") from exc

    members: list[ArchiveMember] = []
    seen: set[str] = set()
    total = 0
    try:
        for info in archive.infolist():
            if getattr(info, "isdir", lambda: False)():
                continue
            size = int(getattr(info, "file_size", 0) or 0)
            if size > max_member:
                raise ArchiveError(
                    f"{info.filename} exceeds max size of {max_member} bytes"
                )
            try:
                data = archive.read(info)
            except Exception as exc:
                raise ArchiveError(f"cannot read {info.filename}: {exc}") from exc
            total += len(data)
            if total > max_total:
                raise ArchiveError(f"archive exceeds max unpacked size of {max_total} bytes")
            item = _accept_member(info.filename, data, seen)
            if item is None:
                continue
            members.append(item)
            if len(members) > max_files:
                raise ArchiveError(f"archive has more than {max_files} documents")
    finally:
        archive.close()
    return members


def extract_archive(raw: bytes, filename: str) -> list[ArchiveMember]:
    suffix = PurePosixPath(filename.replace("\\", "/")).suffix.casefold()
    if suffix == ".zip":
        members = _extract_zip(raw)
    elif suffix == ".rar":
        members = _extract_rar(raw)
    else:
        raise ArchiveError(f"unsupported archive format {suffix or '(none)'}")
    if not members:
        raise ArchiveError("archive has no PDF/JPEG/PNG/TIFF documents")
    return members


def skipped_names(raw: bytes, filename: str, kept: Iterable[str]) -> list[str]:
    """Best-effort list of archive entries that were not queued."""
    kept_set = {name.casefold() for name in kept}
    names: list[str] = []
    suffix = PurePosixPath(filename.replace("\\", "/")).suffix.casefold()
    try:
        if suffix == ".zip":
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                candidates = [info.filename for info in archive.infolist() if not info.is_dir()]
        else:
            return names
    except zipfile.BadZipFile:
        return names
    for name in candidates:
        safe = _safe_basename(name)
        if not safe or safe.casefold() in kept_set:
            continue
        names.append(safe)
    return names
