from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .compare import compare_manifests
from .manifest import ManifestError, load_manifest, normalize_exclude, scan_directory, write_manifest

EXIT_OK = 0
EXIT_DIFFERENT = 1
EXIT_USAGE_OR_INPUT = 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fileledger",
        description="Create deterministic file manifests, compare them, and verify directories.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot = subparsers.add_parser("snapshot", help="scan a directory and write a manifest")
    snapshot.add_argument("root", type=Path, help="directory to scan recursively")
    snapshot.add_argument("manifest", type=Path, help="output JSON manifest path")
    snapshot.add_argument("--exclude", action="append", default=[], metavar="RELATIVE_PATH")

    diff = subparsers.add_parser("diff", help="compare two manifest files")
    diff.add_argument("old_manifest", type=Path)
    diff.add_argument("new_manifest", type=Path)
    diff.add_argument("--format", choices=("json", "text"), default="json")

    verify = subparsers.add_parser("verify", help="compare a directory with a historical manifest")
    verify.add_argument("root", type=Path, help="directory to scan recursively")
    verify.add_argument("manifest", type=Path, help="expected JSON manifest")
    verify.add_argument("--exclude", action="append", default=[], metavar="RELATIVE_PATH")
    verify.add_argument("--format", choices=("json", "text"), default="json")

    return parser


def _print_json(value: object) -> None:
    json.dump(value, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def _print_changes(changes, output_format: str) -> None:
    if output_format == "json":
        _print_json(changes.to_dict())
    else:
        sys.stdout.write(changes.to_text())


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot":
            excludes = [normalize_exclude(value) for value in args.exclude]
            manifest = scan_directory(args.root, excludes)
            write_manifest(manifest, args.manifest)
            _print_json({"files": len(manifest.files), "manifest": str(args.manifest)})
            return EXIT_OK

        if args.command == "diff":
            old = load_manifest(args.old_manifest)
            new = load_manifest(args.new_manifest)
            changes = compare_manifests(old, new)
            _print_changes(changes, args.format)
            return EXIT_OK if changes.matches else EXIT_DIFFERENT

        if args.command == "verify":
            excludes = [normalize_exclude(value) for value in args.exclude]
            expected = load_manifest(args.manifest)
            actual = scan_directory(args.root, excludes)
            changes = compare_manifests(expected, actual)
            _print_changes(changes, args.format)
            return EXIT_OK if changes.matches else EXIT_DIFFERENT
    except (FileNotFoundError, NotADirectoryError, PermissionError, ManifestError, OSError) as exc:
        print(f"fileledger: error: {exc}", file=sys.stderr)
        return EXIT_USAGE_OR_INPUT

    parser.error(f"unknown command: {args.command}")
    return EXIT_USAGE_OR_INPUT


if __name__ == "__main__":
    raise SystemExit(main())
