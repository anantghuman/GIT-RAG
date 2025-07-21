import os
import subprocess
from ingest_cli import get_language

def setup_tree_sitter_languages():
    """Clone tree-sitter language repos"""
    os.makedirs("vendor", exist_ok=True)
    
    lang_repos = {
        'Python': 'https://github.com/tree-sitter/tree-sitter-python',
        'JavaScript': 'https://github.com/tree-sitter/tree-sitter-javascript',
        'TypeScript': 'https://github.com/tree-sitter/tree-sitter-typescript',
        'Java': 'https://github.com/tree-sitter/tree-sitter-java',
        'Go': 'https://github.com/tree-sitter/tree-sitter-go',
        'Rust': 'https://github.com/tree-sitter/tree-sitter-rust',
        'C': 'https://github.com/tree-sitter/tree-sitter-c',
        'C++': 'https://github.com/tree-sitter/tree-sitter-cpp',
    }
    
    languages = get_language()
    if isinstance(languages, dict):
        language_names = list(languages.keys())
    else:
        language_names = languages
    
    for lang in language_names:
        if lang in lang_repos:
            vendor_path = f"vendor/tree-sitter-{lang.lower()}"
            if not os.path.exists(vendor_path):
                print(f"Cloning {lang} parser...")
                subprocess.run(["git", "clone", "--depth", "1", lang_repos[lang], vendor_path], check=True)
            else:
                print(f"{lang} parser already exists")

if __name__ == "__main__":
    setup_tree_sitter_languages()
