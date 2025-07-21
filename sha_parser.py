import subprocess, os
from dotenv import load_dotenv
from repo_utils import get_repo_path  # Import from repo_utils
# REMOVED the circular import

load_dotenv()

def get_branches_for_sha(sha):
    """Get all branches that contain this SHA"""
    cmd = ["git", "--git-dir", get_repo_path(), "branch", "--contains", sha, "-r"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    branches = [b.strip() for b in result.stdout.split('\n') if b.strip()]
    return branches

def get_changed_files(sha):
    """Get files changed in this commit"""
    # First check if this is the initial commit
    cmd_parents = ["git", "--git-dir", get_repo_path(), "show", "--format=%P", "-s", sha]
    parents = subprocess.run(cmd_parents, capture_output=True, text=True).stdout.strip()
    
    if not parents:  # Initial commit
        # For initial commit, list all files
        cmd = ["git", "--git-dir", get_repo_path(), "ls-tree", "-r", "--name-only", sha]
    else:
        # For other commits, show changed files
        cmd = ["git", "--git-dir", get_repo_path(), "show", "--name-only", "--format=", sha]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    files = [f.strip() for f in result.stdout.split('\n') if f.strip()]
    return files

def get_file_at_sha(sha, file_path):
    """Get complete file content at a specific SHA"""
    cmd = ["git", "--git-dir", get_repo_path(), "show", f"{sha}:{file_path}"]
    try:
        content = subprocess.check_output(cmd).decode('utf-8')
        return content
    except subprocess.CalledProcessError:
        return None

def get_diff_for_file(sha, file_path):
    """Get the diff for a specific file in a commit"""
    cmd = ["git", "--git-dir", get_repo_path(), "show", sha, "--", file_path]
    try:
        diff = subprocess.check_output(cmd).decode('utf-8')
        return diff
    except subprocess.CalledProcessError:
        return None

def get_commit_info(sha):  # Remove repo_path parameter
    """Get commit metadata"""
    cmd = ["git", "--git-dir", get_repo_path(), "show", "--format=%an|%ae|%at|%s", "-s", sha]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    parts = result.stdout.strip().split('|')
    return {
        'author': parts[0] if len(parts) > 0 else '',
        'email': parts[1] if len(parts) > 1 else '',
        'timestamp': parts[2] if len(parts) > 2 else '',
        'message': parts[3] if len(parts) > 3 else ''
    }
