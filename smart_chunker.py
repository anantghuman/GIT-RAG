import hashlib
import difflib
from typing import Dict, List, Optional
import subprocess
from tree_sitter import Node

def calculate_file_change_ratio(current_content: str, parent_content: str) -> float:
    """Calculate the percentage of file that changed"""
    if not parent_content:
        return 1.0
    
    current_lines = current_content.split('\n')
    parent_lines = parent_content.split('\n')
    
    # Use difflib to get the actual changed lines
    differ = difflib.unified_diff(parent_lines, current_lines, lineterm='')
    changed_lines = sum(1 for line in differ if line.startswith(('+', '-')) and not line.startswith(('+++', '---')))
    
    total_lines = max(len(current_lines), len(parent_lines))
    return changed_lines / max(total_lines, 1)

def get_function_hash(content: str) -> str:
    """Generate a content-based hash for deduplication"""
    # Normalize the content (remove extra whitespace, comments)
    normalized = '\n'.join(line.strip() for line in content.split('\n') if line.strip() and not line.strip().startswith('#'))
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]

def extract_changed_functions(diff: str, file_path: str) -> List[Dict]:
    """Extract which functions were changed from a diff"""
    changed_functions = []
    current_function = None
    
    for line in diff.split('\n'):
        # Look for function definitions in the diff context
        if line.startswith('@@'):
            # Extract line numbers from diff header
            import re
            match = re.search(r'@@ -\d+,\d+ \+(\d+),(\d+) @@', line)
            if match:
                start_line = int(match.group(1))
                
        elif 'def ' in line or 'function ' in line or 'func ' in line:
            # Simple heuristic to detect function changes
            if line.startswith(('+', '-')):
                func_name = line.split('(')[0].split()[-1] if '(' in line else 'unknown'
                changed_functions.append({
                    'name': func_name,
                    'type': 'added' if line.startswith('+') else 'removed'
                })
    
    return changed_functions

class SmartChunker:
    def __init__(self, repo_path: str, change_threshold: float = 0.3):
        self.repo_path = repo_path
        self.change_threshold = change_threshold
        self.content_cache = {}  # Cache for deduplication
        self.snapshot_interval = 10  # Force snapshot every N commits
        
    def should_store_full_content(self, sha: str, file_path: str, commit_graph: Dict, commit_count: int) -> bool:
        """Determine if we should store full content or just diff"""
        commit_info = commit_graph[sha]
        
        # Always store full content for:
        # 1. First commit (no parents)
        if not commit_info['parents']:
            return True
            
        # 2. Merge commits (multiple parents - complex history)
        if len(commit_info['parents']) > 1:
            return True
            
        # 3. Periodic snapshots for efficient reconstruction
        if commit_count % self.snapshot_interval == 0:
            return True
            
        # 4. Check change ratio
        parent_sha = commit_info['parents'][0]
        try:
            current_content = self.get_file_content(sha, file_path)
            parent_content = self.get_file_content(parent_sha, file_path)
            
            if not parent_content:  # New file
                return True
                
            change_ratio = calculate_file_change_ratio(current_content, parent_content)
            return change_ratio > self.change_threshold
            
        except:
            # If we can't determine, store full content to be safe
            return True
    
    def get_file_content(self, sha: str, file_path: str) -> Optional[str]:
        """Get file content at a specific SHA"""
        cmd = ["git", "--git-dir", self.repo_path, "show", f"{sha}:{file_path}"]
        try:
            return subprocess.check_output(cmd).decode('utf-8')
        except subprocess.CalledProcessError:
            return None
    
    def chunk_with_deduplication(self, sha: str, file_path: str, parser, language: str, 
                                commit_graph: Dict, commit_count: int) -> List[Dict]:
        """Smart chunking with content deduplication"""
        chunks = []
        
        # Determine storage strategy
        store_full = self.should_store_full_content(sha, file_path, commit_graph, commit_count)
        
        if store_full:
            # Store full content with function-level deduplication
            content = self.get_file_content(sha, file_path)
            if not content:
                return []
                
            tree = parser.parse(bytes(content, 'utf8'))
            
            for node in self.traverse_tree(tree.root_node):
                if node.type in ['function_definition', 'class_definition', 'method_definition']:
                    func_content = content[node.start_byte:node.end_byte]
                    func_hash = get_function_hash(func_content)
                    
                    # Check if we've seen this exact function before
                    if func_hash in self.content_cache:
                        # Update the existing entry to include this SHA
                        existing_chunk_id = self.content_cache[func_hash]
                        chunks.append({
                            'type': 'reference',
                            'content_hash': func_hash,
                            'referenced_chunk_id': existing_chunk_id,
                            'sha': sha,
                            'path': file_path,
                            'storage_type': 'deduplicated'
                        })
                    else:
                        # New function content
                        chunk = {
                            'content': func_content,
                            'content_hash': func_hash,
                            'sha': sha,
                            'path': file_path,
                            'language': language,
                            'type': 'code',
                            'storage_type': 'full_snapshot' if commit_count % self.snapshot_interval == 0 else 'full',
                            'node_type': node.type,
                            'line_start': node.start_point[0],
                            'line_end': node.end_point[0],
                            'function_name': self.extract_function_name(node, content)
                        }
                        chunks.append(chunk)
                        # Cache this content
                        self.content_cache[func_hash] = f"{sha}_{file_path}_{node.start_point[0]}"
        else:
            # Store only diff
            parent_sha = commit_graph[sha]['parents'][0]
            diff = self.get_file_diff(sha, file_path)
            
            if diff:
                changed_functions = extract_changed_functions(diff, file_path)
                
                diff_chunk = {
                    'content': diff,
                    'sha': sha,
                    'path': file_path,
                    'type': 'diff',
                    'storage_type': 'incremental',
                    'parent_sha': parent_sha,
                    'changed_functions': changed_functions,
                    'language': language,
                    'line_start': 0,
                    'line_end': 0
                }
                chunks.append(diff_chunk)
        
        return chunks
    
    def get_file_diff(self, sha: str, file_path: str) -> Optional[str]:
        """Get the diff for a file in a commit"""
        cmd = ["git", "--git-dir", self.repo_path, "show", sha, "--", file_path]
        try:
            return subprocess.check_output(cmd).decode('utf-8')
        except subprocess.CalledProcessError:
            return None
    
    def traverse_tree(self, node: Node):
        """Recursively traverse the tree and yield nodes"""
        yield node
        for child in node.children:
            yield from self.traverse_tree(child)
    
    def extract_function_name(self, node: Node, content: str) -> str:
        """Extract function name from a node"""
        # This is language-specific, but here's a simple approach
        for child in node.children:
            if child.type in ['identifier', 'property_identifier']:
                return content[child.start_byte:child.end_byte]
        return "unknown"
