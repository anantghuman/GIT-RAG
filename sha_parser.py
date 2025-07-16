import subprocess, os
from dotenv import load_dotenv
from ingest_cli import get_language

load_dotenv()

import json

def get_repo_path():
    with open("commit_graph.json", "r") as f:
        data = json.load(f)
        return data['repo_path']

def get_branches_for_sha(sha):
    """Get all branches that contain this SHA"""
    cmd = ["git", "--git-dir", get_repo_path(), "branch", "--contains", sha, "-r"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    branches = [b.strip() for b in result.stdout.split('\n') if b.strip()]
    return branches

def get_changed_files(sha):
    """Get files changed in this commit"""
    cmd = ["git", "--git-dir", os.getenv("REPO"), "show", "--name-only", "--format=", sha]
    result = subprocess.run(cmd, capture_output=True, text=True)
    files = [f.strip() for f in result.stdout.split('\n') if f.strip()]
    return files

def get_file_at_sha(sha, file_path):
    """Get complete file content at a specific SHA"""
    cmd = ["git", "--git-dir", os.getenv("REPO"), "show", f"{sha}:{file_path}"]
    try:
        content = subprocess.check_output(cmd).decode('utf-8')
        return content
    except subprocess.CalledProcessError:
        # File might not exist at this SHA
        return None

def get_diff_for_file(sha, file_path):
    """Get the diff for a specific file in a commit"""
    cmd = ["git", "--git-dir", os.getenv("REPO"), "show", sha, "--", file_path]
    diff = subprocess.check_output(cmd).decode('utf-8')
    return diff

def get_commit_info(sha, repo_path):
    """Get commit metadata"""
    cmd = ["git", "--git-dir", repo_path, "show", "--format=%an|%ae|%at|%s", "-s", sha]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    parts = result.stdout.strip().split('|')
    return {
        'author': parts[0],
        'email': parts[1],
        'timestamp': parts[2],
        'message': parts[3]
    }

def setup_tree_sitter_languages():
    """Clone tree-sitter language repos"""
    os.makedirs("vendor", exist_ok=True)
    
    lang_repos = {
        'python': 'https://github.com/tree-sitter/tree-sitter-python',
        'javascript': 'https://github.com/tree-sitter/tree-sitter-javascript',
        'typescript': 'https://github.com/tree-sitter/tree-sitter-typescript',
        'java': 'https://github.com/tree-sitter/tree-sitter-java',
        'go': 'https://github.com/tree-sitter/tree-sitter-go',
        'rust': 'https://github.com/tree-sitter/tree-sitter-rust',
    }
    
    for lang in get_language():
        if lang not in lang_repos:
            print(f"Unsupported language: {lang}")
            continue
        vendor_path = f"vendor/tree-sitter-{lang}"
        if not os.path.exists(vendor_path):
            print(f"Cloning {lang} parser...")
            subprocess.run(["git", "clone", lang_repos[lang], vendor_path], check=True)
        else:
            print(f"{lang} parser already exists")

if __name__ == "__main__":
    setup_tree_sitter_languages()
