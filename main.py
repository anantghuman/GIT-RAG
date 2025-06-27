import os
from dotenv import load_dotenv
import subprocess, os, json, sys

load_dotenv()

# pc = pc(api_key=os.getenv('PINECONE_API_KEY'))

repo_url = os.getenv('REPO_NAME')

repo = Repo.clone_from(repo_url, os.getenv('LOCAL_CLONE_DIR'))
tree = repo.head.commit.tree
prev_commits = list(repo.iter_commits(all=True))
tree = prev_commits[0].tree