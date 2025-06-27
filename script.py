import os
import subprocess
from dotenv import load_dotenv

load_dotenv()

REPO_NAME = os.getenv("REPO_NAME")
print(f"Cloning repository: {REPO_NAME}")

os.chdir(os.getenv("CLONE_REPO_DIR"))
os.makedirs("repos", exist_ok=True)

subprocess.run(["git", "clone", "--mirror", REPO_NAME, "repos/requests.git"], check=True)

os.chdir(os.getenv("PROJECT_DIR"))

with open("shas.txt", "w") as f:
    subprocess.run(
        ["git", "--git-dir", "../repos/requests.git", "log", "--all", "--pretty=%H"],
        stdout=f,
        check=True
    )
