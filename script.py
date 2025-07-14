import os
import subprocess
import json
from dotenv import load_dotenv

load_dotenv()

# Get environment variables
REPO_NAME = os.getenv("REPO_NAME")
CLONE_REPO_DIR = os.getenv("CLONE_REPO_DIR")  # This is /Users/anantghuman/Coding/GIT-RAG/Repos
PROJECT_DIR = os.getenv("PROJECT_DIR")

# Extract repository name from URL
repo_basename = os.path.basename(REPO_NAME).replace('.git', '')

# Since CLONE_REPO_DIR already contains "Repos", just use it directly
# Don't add another "repos" subdirectory
REPO_PATH = os.path.join(CLONE_REPO_DIR, f"{repo_basename}.git")

print(f"Cloning repository: {REPO_NAME}")
print(f"Repository will be at: {REPO_PATH}")

# Create the CLONE_REPO_DIR if it doesn't exist (but don't create a subdirectory)
os.makedirs(CLONE_REPO_DIR, exist_ok=True)

# Check if repository already exists
if os.path.exists(REPO_PATH):
    print(f"Repository already exists at {REPO_PATH}")
    print("Fetching latest updates...")
    subprocess.run(["git", "--git-dir", REPO_PATH, "fetch", "--all"], check=True)
else:
    print(f"Cloning repository to {REPO_PATH}")
    # Clone directly without changing directories
    subprocess.run(["git", "clone", "--mirror", REPO_NAME, REPO_PATH], check=True)

# Change to project directory for subsequent operations
os.chdir(PROJECT_DIR)

print("Building commit graph...")

# Use the dynamic REPO_PATH instead of hardcoded path
result = subprocess.run(
    ["git", "--git-dir", REPO_PATH, "log", "--all", 
     "--pretty=format:%H|%P|%an|%ae|%at|%s|%D"],
    capture_output=True,
    text=True,
    check=True
)

# Get branch information
branch_result = subprocess.run(
    ["git", "--git-dir", REPO_PATH, "for-each-ref", 
     "--format=%(refname:short)|%(objectname)", "refs/heads/"],
    capture_output=True,
    text=True,
    check=True
)

print("Branch output:", branch_result.stdout)

# Build the commit graph
commit_graph = {}
for line in result.stdout.strip().split('\n'):
    if not line:
        continue
    parts = line.split('|', 6)  # Limit split to handle commit messages with |
    if len(parts) >= 6:
        sha = parts[0]
        parents = parts[1].split() if parts[1] else []
        
        commit_graph[sha] = {
            'sha': sha,
            'parents': parents,
            'author': parts[2],
            'email': parts[3],
            'timestamp': parts[4],
            'message': parts[5],
            'refs': parts[6].split(', ') if len(parts) > 6 and parts[6] else []
        }

# Add children relationships
for sha, commit in commit_graph.items():
    commit['children'] = []

for sha, commit in commit_graph.items():
    for parent_sha in commit['parents']:
        if parent_sha in commit_graph:
            commit_graph[parent_sha]['children'].append(sha)

# Parse branch tips
branch_tips = {}
for line in branch_result.stdout.strip().split('\n'):
    if line:
        parts = line.split('|')
        if len(parts) == 2:
            branch, sha = parts
            branch_tips[branch] = sha

# Save the graph, branch tips, and repo path
with open("commit_graph.json", "w") as f:
    json.dump({
        'graph': commit_graph,
        'branch_tips': branch_tips,
        'repo_path': REPO_PATH  # Save for other scripts
    }, f, indent=2)

# Save just the SHAs for backward compatibility
with open("shas.txt", "w") as f:
    f.write('\n'.join(commit_graph.keys()))

print(f"Saved commit graph with {len(commit_graph)} commits")
print(f"Repository path: {REPO_PATH}")
print(f"Found {len(branch_tips)} branches: {list(branch_tips.keys())}")