import subprocess, os, json, concurrent.futures, pathlib, base64, requests
from tree_sitter import Language, Parser
from dotenv import load_dotenv

load_dotenv()

REPO = os.path.join(os.getenv("CLONE_REPO_DIR"), "requests.git")
BUNDLE = "build/my_langs.so"



def get_language():
    user = os.getenv("USER")
    repo = os.getenv("REPO")
    if not user or not repo:
        print("USER or REPO environment variable is not set.")
        return []
 
    url = f"https://api.github.com/repos/{user}/{repo}/languages"
    print(f"Requesting: {url}")
    headers = {}
    headers['Authorization'] = f'token {os.getenv("GITHUB_ACCESS_TOKEN")}'

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        languages = response.json()
        print(list(languages.keys()))
    else:
        print(f"Failed to fetch languages: {response.text}")
        return []
    
get_language()