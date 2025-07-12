import subprocess, os
from dotenv import load_dotenv

load_dotenv()

def get_branches_for_sha(sha):
    """Get all branches that contain this SHA"""
    cmd = ["git", "--git-dir", os.getenv("REPO"), "branch", "--contains", sha, "-r"]
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
