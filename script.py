import os
import subprocess
import json
from dotenv import load_dotenv

load_dotenv()

REPO_NAME = os.getenv("REPO_NAME")
print(f"Cloning repository: {REPO_NAME}")

os.chdir(os.getenv("CLONE_REPO_DIR"))
os.makedirs("repos", exist_ok=True)

subprocess.run(["git", "clone", "--mirror", REPO_NAME, "repos/requests.git"], check=True)

os.chdir(os.getenv("PROJECT_DIR"))

# Instead of just SHAs, capture the full commit graph
print("Building commit graph...")

# Get commits with parent information
result = subprocess.run(
    ["git", "--git-dir", "../repos/requests.git", "log", "--all", 
     "--pretty=format:%H|%P|%an|%ae|%at|%s|%D"],
    capture_output=True,
    text=True,
    check=True
)

# Build the commit graph
commit_graph = {}
for line in result.stdout.strip().split('\n'):
    if not line:
        continue
    parts = line.split('|')
    sha = parts[0]
    parents = parts[1].split() if parts[1] else []
    
    commit_graph[sha] = {
        'sha': sha,
        'parents': parents,
        'author': parts[2],
        'email': parts[3],
        'timestamp': parts[4],
        'message': parts[5],
        'refs': parts[6].split(', ') if parts[6] else []
    }

# Add children relationships
for sha, commit in commit_graph.items():
    commit['children'] = []

for sha, commit in commit_graph.items():
    for parent_sha in commit['parents']:
        if parent_sha in commit_graph:
            commit_graph[parent_sha]['children'].append(sha)

# Get branch tips
result = subprocess.run(
    ["git", "--git-dir", "../repos/requests.git", "for-each-ref", 
     "--format=%(refname:short)|%(objectname)", "refs/heads/"],
    capture_output=True,
    text=True,
    check=True
)

branch_tips = {}
for line in result.stdout.strip().split('\n'):
    if line:
        branch, sha = line.split('|')
        branch_tips[branch] = sha

# Save both the graph and branch tips
with open("commit_graph.json", "w") as f:
    json.dump({
        'graph': commit_graph,
        'branch_tips': branch_tips
    }, f, indent=2)

print(f"Saved commit graph with {len(commit_graph)} commits")