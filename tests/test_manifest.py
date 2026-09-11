from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from fileledger.compare import compare_manifests
from fileledger.manifest import ManifestError, load_manifest, normalize_exclude, scan_directory, write_manifest


def test_snapshot_is_sorted_portable_and_deterministic(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "z").mkdir(parents=True)
    (root / "z" / "b.txt").write_text("beta", encoding="utf-8")
    (root / "a.txt").write_text("alpha", encoding="utf-8")

    manifest = scan_directory(root)
    assert [record.path for record in manifest.files] == ["a.txt", "z/b.txt"]
    assert manifest.files[0].size == 5
    assert manifest.files[0].sha256 == hashlib.sha256(b"alpha").hexdigest()

    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_manifest(manifest, first)
    write_manifest(scan_directory(root), second)
    assert first.read_bytes() == second.read_bytes()


def test_compare_all_change_classes(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "same.txt").write_text("same", encoding="utf-8")
    (root / "modify.txt").write_text("old", encoding="utf-8")
    (root / "remove.txt").write_text("gone", encoding="utf-8")
    before = scan_directory(root)

    (root / "modify.txt").write_text("new", encoding="utf-8")
    (root / "remove.txt").unlink()
    (root / "add.txt").write_text("added", encoding="utf-8")
    after = scan_directory(root)

    changes = compare_manifests(before, after)
    assert changes.added == ("add.txt",)
    assert changes.removed == ("remove.txt",)
    assert changes.modified == ("modify.txt",)
    assert changes.unchanged == ("same.txt",)


def test_load_rejects_unsorted_manifest(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "files": [
                    {"path": "z.txt", "size": 0, "sha256": "0" * 64},
                    {"path": "a.txt", "size": 0, "sha256": "0" * 64},
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="sorted"):
        load_manifest(path)


def test_exclude_file_and_subtree_and_validation(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "cache" / "nested").mkdir(parents=True)
    (root / "keep.txt").write_text("keep", encoding="utf-8")
    (root / "skip.txt").write_text("skip", encoding="utf-8")
    (root / "cache" / "nested" / "x.bin").write_bytes(b"\x00\xff")

    manifest = scan_directory(root, ["skip.txt", "cache"])
    assert [record.path for record in manifest.files] == ["keep.txt"]

    for invalid in ["", ".", "..", "a/../b", "/absolute", "C:\\absolute"]:
        with pytest.raises(ManifestError):
            normalize_exclude(invalid)


def test_unicode_binary_and_empty_directory(tmp_path: Path) -> None:
    root = tmp_path / "根"
    (root / "空目录").mkdir(parents=True)
    (root / "子目录").mkdir()
    (root / "子目录" / "你好.bin").write_bytes(bytes(range(256)))

    manifest = scan_directory(root)
    assert [record.path for record in manifest.files] == ["子目录/你好.bin"]
    assert manifest.files[0].size == 256
    assert manifest.files[0].sha256 == hashlib.sha256(bytes(range(256))).hexdigest()


def test_write_requires_existing_parent_and_refuses_overwrite(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    manifest = scan_directory(root)

    with pytest.raises(FileNotFoundError, match="parent"):
        write_manifest(manifest, tmp_path / "missing" / "out.json")

    destination = tmp_path / "out.json"
    destination.write_text("sentinel", encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_manifest(manifest, destination)
    assert destination.read_text(encoding="utf-8") == "sentinel"


def test_write_cleans_partial_file_on_failure(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "root"
    root.mkdir()
    manifest = scan_directory(root)
    destination = tmp_path / "partial.json"
    original_open = Path.open

    class FailingWriter:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            self.handle.__enter__()
            return self

        def write(self, text: str) -> int:
            self.handle.write(text[:5])
            self.handle.flush()
            raise OSError("simulated write failure")

        def __exit__(self, exc_type, exc, tb):
            return self.handle.__exit__(exc_type, exc, tb)

    def failing_open(path: Path, *args, **kwargs):
        handle = original_open(path, *args, **kwargs)
        if path == destination:
            return FailingWriter(handle)
        return handle

    monkeypatch.setattr(Path, "open", failing_open)
    with pytest.raises(OSError, match="simulated write failure"):
        write_manifest(manifest, destination)
    assert not destination.exists()


def test_symlink_is_rejected_when_supported(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = root / "target.txt"
    target.write_text("x", encoding="utf-8")
    link = root / "link.txt"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available in this environment")
    with pytest.raises(ManifestError, match="special filesystem entry"):
        scan_directory(root)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction test")
def test_windows_junction_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    target = tmp_path / "target"
    root.mkdir()
    target.mkdir()
    junction = root / "junction"

    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.skip(f"junction creation unavailable: {completed.stderr or completed.stdout}")

    with pytest.raises(ManifestError, match="special filesystem entry"):
        scan_directory(root)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction test")
def test_excluded_windows_junction_is_still_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    target = tmp_path / "target"
    root.mkdir()
    target.mkdir()
    junction = root / "junction"

    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.skip(f"junction creation unavailable: {completed.stderr or completed.stdout}")

    with pytest.raises(ManifestError, match="special filesystem entry"):
        scan_directory(root, ["junction"])
