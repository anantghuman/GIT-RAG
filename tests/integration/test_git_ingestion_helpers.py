import subprocess

from gitrag.git import build_commit_graph, changed_files, clone_or_fetch_mirror, list_refs, rev_list_between


def run(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def test_git_helpers_handle_branches_merges_and_deltas(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run(["git", "init", "-b", "main"], repo)
    run(["git", "config", "user.email", "dev@example.com"], repo)
    run(["git", "config", "user.name", "Dev"], repo)
    (repo / "app.py").write_text("def one():\n    return 1\n", encoding="utf-8")
    run(["git", "add", "app.py"], repo)
    run(["git", "commit", "-m", "initial"], repo)
    initial = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()

    run(["git", "checkout", "-b", "feature"], repo)
    (repo / "app.py").write_text("def one():\n    return 1\n\ndef two():\n    return 2\n", encoding="utf-8")
    run(["git", "commit", "-am", "add two"], repo)
    feature_tip = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()

    clone_dir = tmp_path / "mirrors"
    mirror = clone_or_fetch_mirror(str(repo), clone_dir)
    refs = list_refs(mirror)
    graph = build_commit_graph(mirror)
    delta = rev_list_between(mirror, initial, feature_tip)
    files = changed_files(mirror, feature_tip)

    assert any(ref.name.endswith("feature") for ref in refs)
    assert initial in graph
    assert feature_tip in graph
    assert delta == [feature_tip]
    assert files[0].path == "app.py"
