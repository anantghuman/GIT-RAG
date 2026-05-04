"""Tree-sitter parsing helpers for code chunking."""
from pathlib import Path
import os
import subprocess

import requests
import tree_sitter
from dotenv import load_dotenv

from repo_utils import get_repo_path

load_dotenv()


def _import_optional(module_name):
    try:
        return __import__(module_name)
    except Exception:
        return None


tsjs = _import_optional("tree_sitter_javascript")
tspy = _import_optional("tree_sitter_python")
tsts = _import_optional("tree_sitter_typescript")
tsjava = _import_optional("tree_sitter_java")
tsgo = _import_optional("tree_sitter_go")


EXT_TO_LANG = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".go": "Go",
}


def get_language():
    """Fetch repo languages from GitHub. Returns a dict {Language: bytes} or {} on failure."""
    user = os.getenv("USER")
    repo = os.getenv("REPO")
    if not user or not repo:
        print("USER or REPO env var not set; skipping GitHub language lookup.")
        return {}

    url = f"https://api.github.com/repos/{user}/{repo}/languages"
    headers = {}
    token = os.getenv("GITHUB_ACCESS_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        print(f"GitHub languages fetch failed ({resp.status_code}): {resp.text[:200]}")
    except Exception as e:
        print(f"GitHub languages fetch error: {e}")
    return {}


def get_file_language(file_path, supported_languages):
    ext = Path(file_path).suffix.lower()
    lang = EXT_TO_LANG.get(ext)
    if lang and (not supported_languages or lang in supported_languages):
        return lang
    return None


def _ts_language(module, attr=None):
    if module is None:
        return None
    fn = getattr(module, attr, None) if attr else getattr(module, "language", None)
    if fn is None:
        return None
    try:
        return tree_sitter.Language(fn())
    except Exception as e:
        print(f"  failed to load language from {module.__name__}: {e}")
        return None


def build_parsers(languages):
    """Return a dict mapping language name -> tree_sitter.Parser."""
    if isinstance(languages, dict):
        languages = list(languages.keys())
    languages = list(languages) if languages else []

    candidates = {
        "JavaScript": lambda: _ts_language(tsjs),
        "Python": lambda: _ts_language(tspy),
        "TypeScript": lambda: _ts_language(tsts, "language_typescript"),
        "Java": lambda: _ts_language(tsjava),
        "Go": lambda: _ts_language(tsgo),
    }

    parsers = {}
    target = set(languages) if languages else set(candidates.keys())
    for lang in target:
        builder = candidates.get(lang)
        if builder is None:
            continue
        ts_lang = builder()
        if ts_lang is None:
            print(f"  no tree-sitter parser available for {lang}")
            continue
        parsers[lang] = tree_sitter.Parser(ts_lang)
        print(f"  loaded parser: {lang}")
    return parsers


NODE_TYPES = {
    "Python": ["function_definition", "class_definition"],
    "JavaScript": [
        "function_declaration",
        "function_expression",
        "arrow_function",
        "method_definition",
        "class_declaration",
        "variable_declarator",
    ],
    "TypeScript": [
        "function_declaration",
        "function_expression",
        "arrow_function",
        "method_definition",
        "class_declaration",
        "interface_declaration",
    ],
    "Java": ["method_declaration", "class_declaration"],
    "Go": ["function_declaration", "method_declaration"],
}


def chunk_file(sha, file_path, parser, language):
    """Extract function/class chunks from a file at the given SHA."""
    cmd = ["git", "--git-dir", get_repo_path(), "show", f"{sha}:{file_path}"]
    try:
        content_bytes = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        return []

    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return []

    tree = parser.parse(content_bytes)
    target_types = NODE_TYPES.get(language, ["function_definition", "class_definition"])

    chunks = []
    for node in _traverse(tree.root_node):
        if node.type not in target_types:
            continue

        if node.type == "variable_declarator" and language == "JavaScript":
            if not any(c.type in ("arrow_function", "function_expression") for c in node.children):
                continue

        chunks.append(
            {
                "content": content[node.start_byte : node.end_byte],
                "sha": sha,
                "path": file_path,
                "language": language,
                "type": "code",
                "node_type": node.type,
                "line_start": node.start_point[0],
                "line_end": node.end_point[0],
            }
        )

    if not chunks and content.strip():
        chunks.append(
            {
                "content": content[:8000],
                "sha": sha,
                "path": file_path,
                "language": language,
                "type": "file",
                "node_type": "file",
                "line_start": 0,
                "line_end": min(content.count("\n"), 0),
            }
        )

    return chunks


def _traverse(node):
    yield node
    for child in node.children:
        yield from _traverse(child)


traverse_tree = _traverse
