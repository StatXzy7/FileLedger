from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterable

SCHEMA_VERSION = 1


class ManifestError(ValueError):
    """Raised when a manifest cannot be parsed or validated."""


FILE_ATTRIBUTE_REPARSE_POINT = 0x0400


@dataclass(frozen=True, slots=True)
class FileRecord:
    path: str
    size: int
    sha256: str

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "size": self.size, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class Manifest:
    files: tuple[FileRecord, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "files": [record.to_dict() for record in self.files],
        }


def _sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable_relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def normalize_exclude(value: str) -> str:
    """Validate an exclude value and return its portable relative spelling."""
    if value == "":
        raise ManifestError("exclude path must not be empty")
    if PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute():
        raise ManifestError(f"exclude path must be relative: {value!r}")

    portable = value.replace("\\", "/")
    parts = portable.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ManifestError(f"exclude path contains invalid path segments: {value!r}")
    return "/".join(parts)


def _is_excluded(relative_path: str, excludes: tuple[str, ...]) -> bool:
    return any(
        relative_path == excluded or relative_path.startswith(excluded + "/")
        for excluded in excludes
    )


def _is_reparse_point(stat_result: os.stat_result) -> bool:
    attributes = getattr(stat_result, "st_file_attributes", 0)
    return bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT)


def _reject_special(path: Path, stat_result: os.stat_result) -> None:
    if stat.S_ISLNK(stat_result.st_mode) or _is_reparse_point(stat_result):
        raise ManifestError(f"special filesystem entry is not supported: {path}")
    if not (stat.S_ISREG(stat_result.st_mode) or stat.S_ISDIR(stat_result.st_mode)):
        raise ManifestError(f"special filesystem entry is not supported: {path}")


def scan_directory(root: Path, excludes: Iterable[str] = ()) -> Manifest:
    root = root.absolute()
    try:
        root_stat = root.lstat()
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"input directory does not exist: {root}") from exc
    _reject_special(root, root_stat)
    if not stat.S_ISDIR(root_stat.st_mode):
        raise NotADirectoryError(f"input path is not a directory: {root}")

    normalized_excludes = tuple(sorted({normalize_exclude(value) for value in excludes}))

    records: list[FileRecord] = []

    def walk(directory: Path) -> None:
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                relative = _portable_relative(path, root)
                if _is_excluded(relative, normalized_excludes):
                    continue

                entry_stat = entry.stat(follow_symlinks=False)
                _reject_special(path, entry_stat)
                if stat.S_ISDIR(entry_stat.st_mode):
                    walk(path)
                elif stat.S_ISREG(entry_stat.st_mode):
                    records.append(
                        FileRecord(
                            path=relative,
                            size=entry_stat.st_size,
                            sha256=_sha256(path),
                        )
                    )

    walk(root)
    records.sort(key=lambda record: record.path)
    return Manifest(tuple(records))


def write_manifest(manifest: Manifest, destination: Path) -> None:
    parent = destination.parent
    if not parent.exists():
        raise FileNotFoundError(f"output parent directory does not exist: {parent}")
    if not parent.is_dir():
        raise NotADirectoryError(f"output parent path is not a directory: {parent}")
    text = json.dumps(
        manifest.to_dict(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    created = False
    try:
        with destination.open("x", encoding="utf-8", newline="\n") as handle:
            created = True
            handle.write(text + "\n")
    except Exception:
        if created:
            try:
                destination.unlink()
            except FileNotFoundError:
                pass
        raise


def load_manifest(path: Path) -> Manifest:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read manifest {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ManifestError("manifest root must be a JSON object")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError(f"unsupported schema_version: {data.get('schema_version')!r}")
    raw_files = data.get("files")
    if not isinstance(raw_files, list):
        raise ManifestError("manifest 'files' must be a list")

    records: list[FileRecord] = []
    previous = None
    seen: set[str] = set()
    for index, item in enumerate(raw_files):
        if not isinstance(item, dict):
            raise ManifestError(f"files[{index}] must be an object")
        rel = item.get("path")
        size = item.get("size")
        sha256 = item.get("sha256")
        if not isinstance(rel, str) or not rel or "\\" in rel or rel.startswith("/"):
            raise ManifestError(f"files[{index}].path is not a portable relative path")
        parts = rel.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ManifestError(f"files[{index}].path contains invalid path segments")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ManifestError(f"files[{index}].size must be a non-negative integer")
        if not isinstance(sha256, str) or len(sha256) != 64:
            raise ManifestError(f"files[{index}].sha256 must be a 64-character hex string")
        try:
            int(sha256, 16)
        except ValueError as exc:
            raise ManifestError(f"files[{index}].sha256 must be hexadecimal") from exc
        if rel in seen:
            raise ManifestError(f"duplicate manifest path: {rel}")
        if previous is not None and rel < previous:
            raise ManifestError("manifest files must be sorted by path")
        seen.add(rel)
        previous = rel
        records.append(FileRecord(rel, size, sha256.lower()))
    return Manifest(tuple(records))


def records_by_path(records: Iterable[FileRecord]) -> dict[str, FileRecord]:
    return {record.path: record for record in records}
