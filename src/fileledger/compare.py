from __future__ import annotations

from dataclasses import dataclass

from .manifest import FileRecord, Manifest, records_by_path


@dataclass(frozen=True, slots=True)
class ChangeSet:
    added: tuple[str, ...]
    removed: tuple[str, ...]
    modified: tuple[str, ...]
    unchanged: tuple[str, ...]

    @property
    def matches(self) -> bool:
        return not (self.added or self.removed or self.modified)

    def to_dict(self) -> dict[str, object]:
        return {
            "added": list(self.added),
            "removed": list(self.removed),
            "modified": list(self.modified),
            "unchanged": list(self.unchanged),
            "summary": {
                "added": len(self.added),
                "removed": len(self.removed),
                "modified": len(self.modified),
                "unchanged": len(self.unchanged),
            },
        }

    def to_text(self) -> str:
        sections = (
            ("added", self.added),
            ("removed", self.removed),
            ("modified", self.modified),
            ("unchanged", self.unchanged),
        )
        lines: list[str] = []
        for name, paths in sections:
            lines.append(f"{name} ({len(paths)}):")
            lines.extend(f"  {path}" for path in paths)
        return "\n".join(lines) + "\n"


def compare_manifests(old: Manifest, new: Manifest) -> ChangeSet:
    old_map = records_by_path(old.files)
    new_map = records_by_path(new.files)

    old_paths = set(old_map)
    new_paths = set(new_map)
    added = tuple(sorted(new_paths - old_paths))
    removed = tuple(sorted(old_paths - new_paths))

    modified: list[str] = []
    unchanged: list[str] = []
    for path in sorted(old_paths & new_paths):
        before: FileRecord = old_map[path]
        after: FileRecord = new_map[path]
        if before.size != after.size or before.sha256 != after.sha256:
            modified.append(path)
        else:
            unchanged.append(path)

    return ChangeSet(added, removed, tuple(modified), tuple(unchanged))
