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

langs = get_language()
for lang in langs:
    target = f"vendor/tree-sitter-{lang}"
    if not pathlib.Path(target).exists():
        print("→ cloning", lang)
        subprocess.check_call(["git","clone", "--depth","1", GIT_URL.format(lang), target])

LANG_OBJS = {}
for lang_name in langs:
    LANG_OBJS[lang_name] = Language(BUNDLE, lang_name)


get_language()