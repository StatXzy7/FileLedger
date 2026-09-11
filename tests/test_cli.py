from __future__ import annotations

import json
from pathlib import Path

from fileledger.cli import EXIT_DIFFERENT, EXIT_OK, EXIT_USAGE_OR_INPUT, main


def test_snapshot_diff_and_verify(tmp_path: Path, capsys) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "one.txt").write_text("one", encoding="utf-8")
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"

    assert main(["snapshot", str(root), str(before)]) == EXIT_OK
    capsys.readouterr()
    assert main(["verify", str(root), str(before)]) == EXIT_OK
    verify_clean = json.loads(capsys.readouterr().out)
    assert verify_clean["summary"] == {"added": 0, "modified": 0, "removed": 0, "unchanged": 1}

    (root / "one.txt").write_text("changed", encoding="utf-8")
    (root / "two.txt").write_text("two", encoding="utf-8")
    assert main(["snapshot", str(root), str(after)]) == EXIT_OK
    capsys.readouterr()

    assert main(["diff", str(before), str(after)]) == EXIT_DIFFERENT
    diff = json.loads(capsys.readouterr().out)
    assert diff["modified"] == ["one.txt"]
    assert diff["added"] == ["two.txt"]

    assert main(["verify", str(root), str(before)]) == EXIT_DIFFERENT
    capsys.readouterr()


def test_input_error_goes_to_stderr(tmp_path: Path, capsys) -> None:
    code = main(["snapshot", str(tmp_path / "missing"), str(tmp_path / "out.json")])
    captured = capsys.readouterr()
    assert code == EXIT_USAGE_OR_INPUT
    assert captured.out == ""
    assert captured.err.startswith("fileledger: error:")


def test_snapshot_and_verify_share_exclude_semantics(tmp_path: Path, capsys) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "keep.txt").write_text("keep", encoding="utf-8")
    (root / "ignored.txt").write_text("v1", encoding="utf-8")
    (root / "ignored-too.txt").write_text("v1", encoding="utf-8")
    manifest = tmp_path / "manifest.json"

    excludes = ["--exclude", "ignored.txt", "--exclude", "ignored-too.txt"]
    assert main(["snapshot", str(root), str(manifest), *excludes]) == EXIT_OK
    capsys.readouterr()
    (root / "ignored.txt").write_text("v2", encoding="utf-8")
    (root / "ignored-too.txt").write_text("v2", encoding="utf-8")
    assert main(["verify", str(root), str(manifest), *excludes]) == EXIT_OK
    result = json.loads(capsys.readouterr().out)
    assert result["summary"]["unchanged"] == 1


def test_snapshot_does_not_create_output_when_scan_fails(tmp_path: Path, capsys) -> None:
    missing_root = tmp_path / "missing"
    destination = tmp_path / "manifest.json"

    assert main(["snapshot", str(missing_root), str(destination)]) == EXIT_USAGE_OR_INPUT
    capsys.readouterr()
    assert not destination.exists()


def test_text_format_is_sorted_and_preserves_exit_code(tmp_path: Path, capsys) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "z.txt").write_text("old", encoding="utf-8")
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    assert main(["snapshot", str(root), str(before)]) == EXIT_OK
    capsys.readouterr()
    (root / "z.txt").write_text("new", encoding="utf-8")
    (root / "a.txt").write_text("add", encoding="utf-8")
    assert main(["snapshot", str(root), str(after)]) == EXIT_OK
    capsys.readouterr()

    assert main(["diff", str(before), str(after), "--format", "text"]) == EXIT_DIFFERENT
    output = capsys.readouterr().out
    assert output == (
        "added (1):\n  a.txt\n"
        "removed (0):\n"
        "modified (1):\n  z.txt\n"
        "unchanged (0):\n"
    )


def test_cli_rejects_invalid_exclude_and_existing_output(tmp_path: Path, capsys) -> None:
    root = tmp_path / "root"
    root.mkdir()
    output = tmp_path / "out.json"

    assert main(["snapshot", str(root), str(output), "--exclude", "../outside"]) == EXIT_USAGE_OR_INPUT
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "exclude" in captured.err

    output.write_text("existing", encoding="utf-8")
    assert main(["snapshot", str(root), str(output)]) == EXIT_USAGE_OR_INPUT
    captured = capsys.readouterr()
    assert captured.out == ""
    assert output.read_text(encoding="utf-8") == "existing"


def test_verify_text_clean_exit_code(tmp_path: Path, capsys) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "x.txt").write_text("x", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    assert main(["snapshot", str(root), str(manifest)]) == EXIT_OK
    capsys.readouterr()
    assert main(["verify", str(root), str(manifest), "--format", "text"]) == EXIT_OK
    assert "unchanged (1):\n  x.txt\n" in capsys.readouterr().out
