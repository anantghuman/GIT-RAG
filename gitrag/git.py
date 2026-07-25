"""Git mirror, ref, commit, and file-delta utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import subprocess
from typing import Iterable

from .ids import normalize_repo_id


ZERO_SHA = "0" * 40


class GitError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitRef:
    name: str
    sha: str
    ref_type: str


@dataclass(frozen=True)
class CommitRecord:
    sha: str
    parents: list[str]
    author: str
    email: str
    timestamp: int
    message: str
    refs: list[str]
    depth: int = 0


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str
    old_path: str | None = None


EXT_TO_LANG = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".go": "Go",
}


def run_git(repo_path: str | Path | None, args: list[str], *, cwd: str | Path | None = None) -> str:
    cmd = ["git"]
    if repo_path:
        cmd += ["--git-dir", str(repo_path)]
    cmd += args
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise GitError(proc.stderr.strip() or f"git command failed: {' '.join(cmd)}")
    return proc.stdout


def mirror_path(repo_url: str, clone_dir: str | Path) -> Path:
    repo_id = normalize_repo_id(repo_url)
    return Path(clone_dir) / f"{repo_id}.git"


def clone_or_fetch_mirror(repo_url: str, clone_dir: str | Path) -> Path:
    target = mirror_path(repo_url, clone_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        run_git(target, ["fetch", "--all", "--prune", "--tags"])
    else:
        proc = subprocess.run(["git", "clone", "--mirror", repo_url, str(target)], capture_output=True, text=True)
        if proc.returncode != 0:
            raise GitError(proc.stderr.strip() or f"git clone failed for {repo_url}")
    return target


def list_refs(repo_path: str | Path) -> list[GitRef]:
    out = run_git(
        repo_path,
        [
            "for-each-ref",
            "--format=%(refname)|%(refname:short)|%(objectname)",
            "refs/heads/",
            "refs/remotes/",
            "refs/tags/",
        ],
    )
    refs: list[GitRef] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        full, short, sha = line.split("|", 2)
        if full.startswith("refs/tags/"):
            ref_type = "tag"
        elif full.startswith("refs/remotes/"):
            ref_type = "remote_branch"
        else:
            ref_type = "branch"
        refs.append(GitRef(name=short, sha=sha, ref_type=ref_type))
    return refs


def list_commits(repo_path: str | Path, revs: Iterable[str] | None = None) -> list[CommitRecord]:
    selectors = list(revs or ["--all"])
    out = run_git(repo_path, ["log", *selectors, "--pretty=format:%H|%P|%an|%ae|%at|%s|%D"])
    commits: list[CommitRecord] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 6)
        if len(parts) < 6:
            continue
        refs = parts[6].split(", ") if len(parts) > 6 and parts[6] else []
        commits.append(
            CommitRecord(
                sha=parts[0],
                parents=parts[1].split() if parts[1] else [],
                author=parts[2],
                email=parts[3],
                timestamp=int(parts[4] or 0),
                message=parts[5],
                refs=refs,
            )
        )
    return commits


def build_commit_graph(repo_path: str | Path) -> dict[str, dict]:
    commits = {c.sha: c for c in list_commits(repo_path)}
    children: dict[str, list[str]] = {sha: [] for sha in commits}
    for commit in commits.values():
        for parent in commit.parents:
            if parent in children:
                children[parent].append(commit.sha)

    depth_cache: dict[str, int] = {}

    def depth(sha: str) -> int:
        if sha in depth_cache:
            return depth_cache[sha]
        commit = commits.get(sha)
        if commit is None or not commit.parents:
            depth_cache[sha] = 0
        else:
            parent_depths = [depth(parent) for parent in commit.parents if parent in commits]
            depth_cache[sha] = 1 + (max(parent_depths) if parent_depths else 0)
        return depth_cache[sha]

    return {
        sha: {
            "sha": record.sha,
            "parents": record.parents,
            "children": children.get(sha, []),
            "author": record.author,
            "email": record.email,
            "timestamp": record.timestamp,
            "message": record.message,
            "refs": record.refs,
            "depth": depth(sha),
            "is_merge": len(record.parents) > 1,
        }
        for sha, record in commits.items()
    }


def rev_list_between(repo_path: str | Path, before: str | None, after: str) -> list[str]:
    if not before or before == ZERO_SHA:
        args = ["rev-list", "--reverse", after]
    else:
        args = ["rev-list", "--reverse", f"{before}..{after}"]
    out = run_git(repo_path, args)
    return [line.strip() for line in out.splitlines() if line.strip()]


def changed_files(repo_path: str | Path, sha: str) -> list[ChangedFile]:
    parents = run_git(repo_path, ["show", "--format=%P", "-s", sha]).strip().split()
    if not parents:
        out = run_git(repo_path, ["ls-tree", "-r", "--name-only", sha])
        return [ChangedFile(path=line.strip(), status="A") for line in out.splitlines() if line.strip()]

    out = run_git(repo_path, ["diff-tree", "--no-commit-id", "--name-status", "-r", "-m", sha])
    files: list[ChangedFile] = []
    seen: set[tuple[str, str]] = set()
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        if status.startswith("R") and len(parts) >= 3:
            item = ChangedFile(path=parts[2], status="R", old_path=parts[1])
        else:
            item = ChangedFile(path=parts[-1], status=status[:1])
        key = (item.path, item.status)
        if key not in seen:
            files.append(item)
            seen.add(key)
    return files


def file_at_sha(repo_path: str | Path, sha: str, path: str) -> str | None:
    try:
        return run_git(repo_path, ["show", f"{sha}:{path}"])
    except GitError:
        return None


def diff_for_file(repo_path: str | Path, sha: str, path: str) -> str | None:
    try:
        return run_git(repo_path, ["show", "--format=", "--unified=80", sha, "--", path])
    except GitError:
        return None


def refs_containing_commit(repo_path: str | Path, sha: str) -> list[str]:
    out = run_git(repo_path, ["branch", "--all", "--contains", sha, "--format=%(refname:short)"])
    return [line.strip().lstrip("* ").strip() for line in out.splitlines() if line.strip()]


def language_for_path(path: str) -> str | None:
    return EXT_TO_LANG.get(Path(path).suffix.lower())


def repo_display_name(repo_url: str) -> str:
    return os.path.basename(repo_url.rstrip("/")).removesuffix(".git") or normalize_repo_id(repo_url)
