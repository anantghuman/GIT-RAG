"""Clone (mirror) the configured GitHub repo and build a commit DAG json."""
import json
import os
import subprocess

from dotenv import load_dotenv

load_dotenv()


def main():
    repo_url = os.getenv("REPO_NAME")
    clone_dir = os.getenv("CLONE_REPO_DIR")
    project_dir = os.getenv("PROJECT_DIR")

    if not repo_url or not clone_dir:
        raise SystemExit("REPO_NAME and CLONE_REPO_DIR must be set in .env")

    repo_basename = os.path.basename(repo_url).replace(".git", "")
    repo_path = os.path.join(clone_dir, f"{repo_basename}.git")

    print(f"Repo URL : {repo_url}")
    print(f"Mirror at: {repo_path}")

    os.makedirs(clone_dir, exist_ok=True)

    if os.path.exists(repo_path):
        print("Mirror exists; fetching latest refs...")
        subprocess.run(["git", "--git-dir", repo_path, "fetch", "--all", "--prune", "--tags"], check=True)
    else:
        print("Cloning mirror...")
        subprocess.run(["git", "clone", "--mirror", repo_url, repo_path], check=True)

    if project_dir and os.path.isdir(project_dir):
        os.chdir(project_dir)

    print("Building commit graph...")
    log = subprocess.run(
        [
            "git",
            "--git-dir",
            repo_path,
            "log",
            "--all",
            "--pretty=format:%H|%P|%an|%ae|%at|%s|%D",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    refs = subprocess.run(
        [
            "git",
            "--git-dir",
            repo_path,
            "for-each-ref",
            "--format=%(refname:short)|%(objectname)",
            "refs/heads/",
            "refs/remotes/",
            "refs/tags/",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    commit_graph = {}
    for line in log.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|", 6)
        if len(parts) < 6:
            continue
        sha = parts[0]
        commit_graph[sha] = {
            "sha": sha,
            "parents": parts[1].split() if parts[1] else [],
            "author": parts[2],
            "email": parts[3],
            "timestamp": parts[4],
            "message": parts[5],
            "refs": parts[6].split(", ") if len(parts) > 6 and parts[6] else [],
            "children": [],
        }

    for sha, commit in commit_graph.items():
        for parent_sha in commit["parents"]:
            if parent_sha in commit_graph:
                commit_graph[parent_sha]["children"].append(sha)

    branch_tips = {}
    for line in refs.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|")
        if len(parts) == 2:
            branch_tips[parts[0]] = parts[1]

    out = {"graph": commit_graph, "branch_tips": branch_tips, "repo_path": repo_path}
    with open("commit_graph.json", "w") as f:
        json.dump(out, f, indent=2)

    with open("shas.txt", "w") as f:
        f.write("\n".join(commit_graph.keys()))

    print(f"Saved {len(commit_graph)} commits across {len(branch_tips)} refs to commit_graph.json")
    print(f"Branches/refs: {list(branch_tips.keys())[:10]}{'...' if len(branch_tips) > 10 else ''}")


if __name__ == "__main__":
    main()
