"""Snapshot/diff storage policy and storage report helpers."""

from __future__ import annotations

from dataclasses import dataclass
import difflib


@dataclass(frozen=True)
class StorageDecision:
    kind: str
    reason: str


def change_ratio(current_content: str, parent_content: str | None) -> float:
    if not parent_content:
        return 1.0
    current = current_content.splitlines()
    parent = parent_content.splitlines()
    diff = difflib.unified_diff(parent, current, lineterm="")
    changed = sum(
        1
        for line in diff
        if (line.startswith("+") or line.startswith("-")) and not line.startswith("+++") and not line.startswith("---")
    )
    return changed / max(len(current), len(parent), 1)


def choose_storage_kind(
    *,
    has_parent: bool,
    is_merge: bool,
    version_index: int,
    current_content: str,
    parent_content: str | None,
    snapshot_interval: int,
    change_threshold: float,
) -> StorageDecision:
    if not has_parent:
        return StorageDecision(kind="snapshot", reason="initial_commit")
    if is_merge:
        return StorageDecision(kind="snapshot", reason="merge_commit")
    if snapshot_interval > 0 and version_index % snapshot_interval == 0:
        return StorageDecision(kind="snapshot", reason="periodic_snapshot")
    if change_ratio(current_content, parent_content) > change_threshold:
        return StorageDecision(kind="snapshot", reason="large_change")
    return StorageDecision(kind="diff", reason="incremental_delta")


def storage_reduction(naive_bytes: int, stored_bytes: int) -> float:
    if naive_bytes <= 0:
        return 0.0
    return max(0.0, 1.0 - (stored_bytes / naive_bytes))
