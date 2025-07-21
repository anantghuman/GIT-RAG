# ingest_cli.py
from pathlib import Path
import subprocess, os, requests
import tree_sitter
import tree_sitter_javascript as tsjs
from dotenv import load_dotenv
from repo_utils import get_repo_path

load_dotenv()

def get_language():
    user = os.getenv("USER")
    repo = os.getenv("REPO")
    if not user or not repo:
        print("USER or REPO environment variable is not set.")
        return []
 
    url = f"https://api.github.com/repos/{user}/{repo}/languages"
    print(f"Requesting: {url}")
    headers = {}
    token = os.getenv("GITHUB_ACCESS_TOKEN")
    if token:
        headers['Authorization'] = f'token {token}'

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
    """Build parsers using pre-built tree-sitter language packages"""
    parsers = {}
    
    # Map of available pre-built language packages
    language_modules = {
        'JavaScript': tsjs,
        # Add more as needed:
        # 'Python': tree_sitter_python,
        # 'TypeScript': tree_sitter_typescript,
    }
    
    for lang in languages:
        if lang in language_modules:
            try:
                # Get the language object from the module
                ts_language = tree_sitter.Language(language_modules[lang].language())
                
                # Create a parser
                parser = tree_sitter.Parser(ts_language)
                parsers[lang] = parser
                print(f"✓ Loaded parser for {lang}")
            except Exception as e:
                print(f"✗ Failed to load parser for {lang}: {e}")
        else:
            print(f"⚠ No pre-built parser available for {lang}")
            print(f"  Install with: pip install tree-sitter-{lang.lower()}")
    
    return parsers

def chunk_file(sha, file_path, parser, language):
    """Extract code chunks from a file"""
    # Get file content at specific SHA
    cmd = ["git", "--git-dir", get_repo_path(), "show", f"{sha}:{file_path}"]
    try:
        content = subprocess.check_output(cmd).decode('utf-8')
    except subprocess.CalledProcessError:
        return []
    
    # Parse with tree-sitter
    tree = parser.parse(bytes(content, 'utf8'))
    
    # Extract functions/classes
    chunks = []
    
    # Language-specific node types for JavaScript
    node_types = {
        'Python': ['function_definition', 'class_definition'],
        'JavaScript': ['function_declaration', 'function_expression', 'arrow_function', 
                      'method_definition', 'class_declaration', 'variable_declarator'],
        'TypeScript': ['function_declaration', 'function_expression', 'arrow_function', 
                      'method_definition', 'class_declaration'],
        'Java': ['method_declaration', 'class_declaration'],
        'Go': ['function_declaration', 'method_declaration'],
        'C': ['function_definition'],
        'C++': ['function_definition', 'class_specifier'],
    }
    
    target_types = node_types.get(language, ['function_definition', 'class_definition'])
    
    # Debug: print some nodes to see what we're getting
    print(f"\n   Parsing {file_path}...")
    print(f"   Root node: {tree.root_node.type}")
    found_types = set()
    
    for node in traverse_tree(tree.root_node):
        found_types.add(node.type)
        if node.type in target_types:
            # For variable declarators, check if it's a function
            if node.type == 'variable_declarator' and language == 'JavaScript':
                # Check if the right side is a function
                has_function = False
                for child in node.children:
                    if child.type in ['arrow_function', 'function_expression']:
                        has_function = True
                        break
                if not has_function:
                    continue
            
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
    
    if not chunks and language == 'JavaScript':
        print(f"   No chunks found. Found node types: {sorted(found_types)[:20]}...")
        print("   Try looking for: lexical_declaration, variable_declaration")
    
    return chunks

def traverse_tree(node):
    """Recursively traverse the tree and yield nodes."""
    yield node
    for child in node.children:
        yield from traverse_tree(child)
