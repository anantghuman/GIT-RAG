import subprocess, os, json, sys
from collections import deque

from ingest_cli import build_parsers, get_language, get_file_language, chunk_file
from sha_parser import get_changed_files, get_commit_info, get_branches_for_sha, get_file_at_sha, get_diff_for_file
from embeddings import generate_embeddings, upsert_embeddings
from pinecone_setup import setup_vector_db
from dag_utils import topological_sort, get_commit_depth, get_branches_containing_commit
from dotenv import load_dotenv

load_dotenv()

def ingest_repository_with_dag():
    # Load the commit graph instead of flat SHA list
    with open("commit_graph.json", "r") as f:
        data = json.load(f)
        commit_graph = data['graph']
        branch_tips = data['branch_tips']
    
    # Get languages and build parsers
    languages = get_language()
    parsers = build_parsers(languages)
    
    # Set up vector DB
    index = setup_vector_db()
    
    # Process commits in topological order
    sorted_commits = topological_sort(commit_graph)
    
    print(f"Processing {len(sorted_commits)} commits in topological order...")
    
    processed = set()
    
    for i, sha in enumerate(sorted_commits):
        if sha in processed:
            continue
            
        print(f"Processing commit {i+1}/{len(sorted_commits)}: {sha[:8]}")
        
        # Get enhanced commit context from the DAG
        commit_data = commit_graph[sha]
        branches = get_branches_containing_commit(sha, commit_graph, branch_tips)
        depth = get_commit_depth(sha, commit_graph)
        
        # Process the commit with DAG context
        chunks = process_commit_with_dag_context(
            sha, commit_data, branches, depth, parsers, languages, commit_graph
        )
        
        # Generate embeddings and store
        if chunks:
            embedded_chunks = generate_embeddings(chunks)
            upsert_embeddings(index, embedded_chunks)
        
        processed.add(sha)

def process_commit_with_dag_context(sha, commit_data, branches, depth, parsers, languages, commit_graph):
    """Process a commit with full DAG context"""
    
    # Get changed files
    changed_files = get_changed_files(sha)
    
    chunks = []
    
    for file_path in changed_files:
        # Determine language
        language = get_file_language(file_path, list(languages.keys()))
        if not language or language not in parsers:
            continue
            
        # Get file content
        full_content = get_file_at_sha(sha, file_path)
        if full_content:
            # Parse and chunk the file
            file_chunks = chunk_file(sha, file_path, parsers[language], language)
            
            # Enhance each chunk with DAG metadata
            for chunk in file_chunks:
                chunk.update({
                    'branches': branches,
                    'parents': commit_data['parents'],
                    'children': commit_data.get('children', []),
                    'depth': depth,
                    'is_merge': len(commit_data['parents']) > 1,
                    'refs': commit_data.get('refs', []),
                    'timestamp': commit_data['timestamp'],
                    'commit_message': commit_data['message']
                })
            chunks.extend(file_chunks)
        
        # Also store the diff with DAG context
        try:
            diff = get_diff_for_file(sha, file_path)
            diff_chunk = {
                'type': 'diff',
                'content': diff,
                'sha': sha,
                'path': file_path,
                'branches': branches,
                'parents': commit_data['parents'],
                'is_merge': len(commit_data['parents']) > 1,
                'depth': depth,
                'commit_message': commit_data['message'],
                'language': language,
                'line_start': 0,
                'line_end': 0
            }
            chunks.append(diff_chunk)
        except:
            pass  # Skip if diff fails
    
    return chunks

def query_by_dag_relationship(index, query, relationship_type):
    """
    Enhanced queries using DAG relationships.
    Examples:
    - Find all changes between two commits
    - Find all commits on a specific branch
    - Find merge commits
    """
    if relationship_type == "between_commits":
        # Find all commits between two SHAs
        start_sha, end_sha = query.split("..")
        # Implementation would filter by depth and ancestry
        
    elif relationship_type == "branch_only":
        # Find commits only on a specific branch
        branch_name = query
        filter_dict = {"branches": {"$in": [branch_name]}}
        
    elif relationship_type == "merge_commits":
        # Find all merge commits
        filter_dict = {"is_merge": True}
    
    # Use the filter in Pinecone query
    # ... query implementation

# Replace the old ingest_repository with the new DAG version
if __name__ == "__main__":
    ingest_repository_with_dag()