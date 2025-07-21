from typing import Optional, Dict, List
from smart_chunker import SmartChunker
import patch_ng
import subprocess
import tempfile
import os


class FileReconstructor:
    def __init__(self, vector_db_index, commit_graph: Dict, repo_path: str):
        self.index = vector_db_index
        self.commit_graph = commit_graph
        self.repo_path = repo_path
        self.chunker = SmartChunker(repo_path)
        self.reconstruction_cache = {}
        
    def reconstruct_file_at_sha(self, sha: str, file_path: str) -> Optional[str]:
        """Reconstruct complete file content at a specific SHA"""
        cache_key = f"{sha}:{file_path}"
        
        # Check cache first
        if cache_key in self.reconstruction_cache:
            return self.reconstruction_cache[cache_key]
        
        # Find the nearest full snapshot
        snapshot_sha, snapshot_content = self.find_nearest_snapshot(sha, file_path)
        
        if not snapshot_sha:
            return None
        
        # If we found the exact SHA, return it
        if snapshot_sha == sha:
            self.reconstruction_cache[cache_key] = snapshot_content
            return snapshot_content
        
        # Otherwise, apply diffs forward to reach the target SHA
        path_to_target = self.find_path_between_commits(snapshot_sha, sha)
        
        if not path_to_target:
            # Try getting it directly from git
            return self.chunker.get_file_content(sha, file_path)
        
        # Apply diffs in sequence
        reconstructed_content = snapshot_content
        for intermediate_sha in path_to_target[1:]:  # Skip the snapshot SHA
            diff = self.get_diff_between_shas(
                path_to_target[path_to_target.index(intermediate_sha) - 1],
                intermediate_sha,
                file_path
            )
            if diff:
                reconstructed_content = self.apply_diff(reconstructed_content, diff)
        
        self.reconstruction_cache[cache_key] = reconstructed_content
        return reconstructed_content
    
    def find_nearest_snapshot(self, sha: str, file_path: str) -> tuple[Optional[str], Optional[str]]:
        """Find the nearest full snapshot of a file"""
        # Query vector DB for full snapshots
        filter_query = {
            "path": file_path,
            "storage_type": {"$in": ["full", "full_snapshot"]}
        }
        
        # Get all snapshots for this file
        results = self.index.query(
            vector=[0] * 1536,  # Dummy vector for metadata-only query
            filter=filter_query,
            top_k=100,
            include_metadata=True
        )
        
        if not results.matches:
            return None, None
        
        # Find the snapshot that's an ancestor of our target SHA
        for match in results.matches:
            snapshot_sha = match.metadata['sha']
            if self.is_ancestor(snapshot_sha, sha):
                # Retrieve the full content from the chunk
                return snapshot_sha, match.metadata.get('content', '')
        
        return None, None
    
    def find_path_between_commits(self, start_sha: str, end_sha: str) -> Optional[List[str]]:
        """Find the path of commits between two SHAs"""
        if start_sha == end_sha:
            return [start_sha]
        
        # BFS to find path
        from collections import deque
        
        queue = deque([(start_sha, [start_sha])])
        visited = {start_sha}
        
        while queue:
            current_sha, path = queue.popleft()
            
            commit = self.commit_graph.get(current_sha)
            if not commit:
                continue
            
            for child_sha in commit.get('children', []):
                if child_sha == end_sha:
                    return path + [child_sha]
                
                if child_sha not in visited:
                    visited.add(child_sha)
                    queue.append((child_sha, path + [child_sha]))
        
        return None
    
    def is_ancestor(self, potential_ancestor: str, sha: str) -> bool:
        """Check if potential_ancestor is an ancestor of sha"""
        if potential_ancestor == sha:
            return True
        
        commit = self.commit_graph.get(sha)
        if not commit or not commit['parents']:
            return False
        
        for parent in commit['parents']:
            if self.is_ancestor(potential_ancestor, parent):
                return True
        
        return False
    
    def get_diff_between_shas(self, parent_sha: str, child_sha: str, file_path: str) -> Optional[str]:
        """Get diff for a specific file between two commits"""
        # First try to get it from vector DB
        filter_query = {
            "sha": child_sha,
            "path": file_path,
            "type": "diff",
            "parent_sha": parent_sha
        }
        
        results = self.index.query(
            vector=[0] * 1536,
            filter=filter_query,
            top_k=1,
            include_metadata=True
        )
        
        if results.matches:
            return results.matches[0].metadata.get('content', '')
        
        # Fallback to git
        cmd = ["git", "--git-dir", self.repo_path, "diff", 
               f"{parent_sha}..{child_sha}", "--", file_path]
        try:
            return subprocess.check_output(cmd).decode('utf-8')
        except:
            return None
    
    def apply_diff(self, content: str, diff: str) -> str:
        """Apply a unified diff to content using patch-ng"""
        # Create a temporary file with the original content
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tmp') as f:
            f.write(content)
            temp_file = f.name

        try:
            # Create a patch object
            pset = patch_ng.fromstring(diff.encode())
        
            # Apply the patch
            success = pset.apply(root=os.path.dirname(temp_file))
        
            if success:
                # Read the patched content
                with open(temp_file, 'r') as f:
                    patched_content = f.read()
                return patched_content
            else:
                print("Failed to apply patch")
                return content
            
        finally:
            # Clean up
            if os.path.exists(temp_file):
                os.unlink(temp_file)

