import json
import os

def get_repo_path():
    """Get the repository path from saved config"""
    try:
        with open("commit_graph.json", "r") as f:
            data = json.load(f)
            return data['repo_path']
    except:
        # Fallback to environment variable
        return os.getenv("REPO")