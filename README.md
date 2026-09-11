# FileLedger

FileLedger is a small local Python 3.11+ command-line tool for deterministic file inventories.
It can snapshot a directory, compare two saved manifests, and verify a current directory against a historical manifest.

## Install

```powershell
python -m pip install -e .
```

No runtime dependencies beyond the Python standard library are used.

## Commands

```text
fileledger snapshot ROOT MANIFEST [--exclude RELATIVE_PATH ...]
fileledger diff OLD_MANIFEST NEW_MANIFEST [--format json|text]
fileledger verify ROOT MANIFEST [--exclude RELATIVE_PATH ...] [--format json|text]
```

`snapshot` recursively scans regular files beneath `ROOT` and writes a JSON manifest.
`diff` compares two manifests and reports added, removed, modified, and unchanged paths.
`verify` rescans `ROOT` and compares the result with `MANIFEST`.

`--exclude` may be repeated. Each value names a relative file or directory subtree and uses the same semantics in `snapshot` and `verify`. Absolute paths, empty paths, `.`, `..`, and paths containing `.` / `..` segments are rejected. Backslashes are normalized to `/` after absolute-path validation.

## Manifest format

Manifests are UTF-8 JSON with a stable schema:

```json
{
  "files": [
    {
      "path": "docs/readme.txt",
      "sha256": "...64 hex characters...",
      "size": 123
    }
  ],
  "schema_version": 1
}
```

Each entry records the path relative to `ROOT`, byte size, and SHA-256 digest. Paths always use `/`, even on Windows. Entries are sorted lexicographically by portable relative path. JSON object keys are also sorted and output uses `\n` line endings, so an unchanged directory produces byte-for-byte identical manifest output.

## Diff / verify output

Both commands write JSON to stdout by default, preserving the original output format:

```json
{
  "added": ["new.txt"],
  "modified": ["changed.txt"],
  "removed": ["old.txt"],
  "summary": {
    "added": 1,
    "modified": 1,
    "removed": 1,
    "unchanged": 2
  },
  "unchanged": ["keep.txt", "nested/stable.txt"]
}
```

Use `--format text` for a human-readable form. Every category includes its count and sorted paths, for example:

```text
added (1):
  new.txt
removed (0):
modified (1):
  changed.txt
unchanged (1):
  keep.txt
```

Errors are written to stderr.

## Exit codes

- `0`: command completed and, for `diff` / `verify`, no differences were found.
- `1`: `diff` / `verify` completed successfully and found one or more differences.
- `2`: invalid/unreadable input, malformed manifest, filesystem error, or CLI usage error.

## Input scope and limitations

- Scans ordinary directories recursively and records ordinary files only.
- Symbolic links, Windows junctions/reparse points, FIFOs, sockets, devices, and other special filesystem entries are rejected with an error. They are never followed or silently skipped.
- Excluded directory subtrees are pruned before inspecting entries inside them.
- File metadata other than relative path, size, and SHA-256 is intentionally ignored; permissions, owner, timestamps, ACLs, extended attributes, directories, and empty directories are not represented.
- The snapshot destination's parent directory must already exist. FileLedger never overwrites an existing manifest. The destination is created only after scanning succeeds; if writing fails after creation, FileLedger attempts to remove the partial output.
- A file changed while it is being hashed can yield a snapshot reflecting the bytes observed during that read. FileLedger does not lock files or provide filesystem-transaction semantics.
- Comparison treats a file as modified when its byte size or SHA-256 differs. Renames appear as one removal plus one addition.
- Manifest paths are validated as portable relative paths and duplicate or unsorted entries are rejected.

## Development

```powershell
python -m pip install -e . pytest
python -m pytest -q
```

See `examples/README.md` for a minimal workflow.
