"""Shared helpers for locating the mirror clone."""
import json
import os


def get_repo_path():
    """Return the path of the bare/mirror git repo. Prefers commit_graph.json."""
    try:
        with open("commit_graph.json") as f:
            return json.load(f)["repo_path"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        pass

    clone_dir = os.getenv("CLONE_REPO_DIR")
    repo_url = os.getenv("REPO_NAME") or ""
    repo_basename = os.path.basename(repo_url).replace(".git", "")
    if clone_dir and repo_basename:
        return os.path.join(clone_dir, f"{repo_basename}.git")

    return os.getenv("REPO")
