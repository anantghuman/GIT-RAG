from pathlib import Path
import subprocess, os, requests
from tree_sitter import Language, Parser
from dotenv import load_dotenv
from sha_parser import get_repo_path

load_dotenv()

REPO = os.path.join(os.getenv("CLONE_REPO_DIR"), "requests.git")
BUNDLE = "build/my_langs.so"

def get_language():
    user = os.getenv("USER")
    repo = get_repo_path()
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
        return languages
    else:
        print(f"Failed to fetch languages: {response.text}")
        return []
    
def get_file_language(file_path, supported_languages):
    """Map file extensions to languages"""
    ext_to_lang = {
        '.py': 'Python',
        '.js': 'JavaScript',
        '.ts': 'TypeScript',
        '.java': 'Java',
        '.cpp': 'C++',
        '.c': 'C',
        '.go': 'Go',
        '.rs': 'Rust',
    }
    
    ext = Path(file_path).suffix.lower()
    lang = ext_to_lang.get(ext)
    
    # Check if language is in supported languages
    if lang and lang in supported_languages:
        return lang
    return None

def build_parsers(languages):
    Language.build_library(
        BUNDLE,
        [f'vendor/tree-sitter-{lang.lower()}' for lang in languages]
    )
    
    parsers = {}
    for lang in languages:
        lang_obj = Language(BUNDLE, lang.lower())
        parser = Parser()
        parser.set_language(lang_obj)
        parsers[lang] = parser
    return parsers

def chunk_file(sha, file_path, parser, language):
    # Get file content at specific SHA
    cmd = ["git", "--git-dir", REPO, "show", f"{sha}:{file_path}"]
    content = subprocess.check_output(cmd).decode('utf-8')
    
    # Parse with tree-sitter
    tree = parser.parse(bytes(content, 'utf8'))
    
    # Extract functions/classes (≈150-300 tokens each)
    chunks = []
    for node in traverse_tree(tree.root_node):
        if node.type in ['function_definition', 'class_definition']:
            chunk = {
                'content': content[node.start_byte:node.end_byte],
                'sha': sha,
                'path': file_path,
                'language': language,
                'type': node.type,
                'line_start': node.start_point[0],
                'line_end': node.end_point[0]
            }
            chunks.append(chunk)
    return chunks

def traverse_tree(node):
    """Recursively traverse the tree and yield nodes."""
    yield node
    for child in node.children:
        yield from traverse_tree(child)