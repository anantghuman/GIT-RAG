import subprocess, os, json, sys
from collections import deque

from ingest_cli import build_parsers, get_language, get_file_language
from sha_parser import get_changed_files, get_commit_info, get_branches_for_sha, get_file_at_sha, get_diff_for_file
from embeddings import generate_embeddings, upsert_embeddings
from pinecone_setup import setup_vector_db
from dag_utils import topological_sort, get_commit_depth, get_branches_containing_commit
from smart_chunker import SmartChunker
from dotenv import load_dotenv

load_dotenv()

def ingest_repository_with_smart_chunking():
    """Ingest repository using smart chunking and deduplication"""
    
    # Load the commit graph
    with open("commit_graph.json", "r") as f:
        data = json.load(f)
        commit_graph = data['graph']
        branch_tips = data['branch_tips']
        repo_path = data['repo_path']
    
    # Get languages and build parsers
    languages = get_language()
    parsers = build_parsers(languages)
    
    # Set up vector DB
    index = setup_vector_db()
    
    # Initialize smart chunker
    chunker = SmartChunker(repo_path)
    
    # Process commits in topological order
    sorted_commits = topological_sort(commit_graph)
    
    print(f"Processing {len(sorted_commits)} commits with smart chunking...")
    
    processed = set()
    commit_count = 0
    total_chunks = 0
    deduplicated_chunks = 0
    
    for i, sha in enumerate(sorted_commits):
        if sha in processed:
            continue
        
        commit_count += 1
        print(f"Processing commit {i+1}/{len(sorted_commits)}: {sha[:8]}")
        
        # Get enhanced commit context
        commit_data = commit_graph[sha]
        branches = get_branches_containing_commit(sha, commit_graph, branch_tips)
        depth = get_commit_depth(sha, commit_graph)
        
        # Process changed files with smart chunking
        chunks = process_commit_smart(
            sha, commit_data, branches, depth, parsers, languages, 
            commit_graph, chunker, commit_count
        )
        
        # Count deduplication
        for chunk in chunks:
            if chunk.get('storage_type') == 'deduplicated':
                deduplicated_chunks += 1
        
        total_chunks += len(chunks)
        
        # Generate embeddings and store
        if chunks:
            # Only generate embeddings for chunks with content
            chunks_with_content = [c for c in chunks if c.get('type') != 'reference']
            if chunks_with_content:
                embedded_chunks = generate_embeddings(chunks_with_content)
                upsert_embeddings(index, embedded_chunks)
        
        processed.add(sha)
        
        # Print stats every 100 commits
        if commit_count % 100 == 0:
            print(f"Stats: {total_chunks} total chunks, {deduplicated_chunks} deduplicated")
            savings = (deduplicated_chunks / max(total_chunks, 1)) * 100
            print(f"Space savings: {savings:.1f}%")
    
    print(f"\nFinal stats:")
    print(f"Total commits: {commit_count}")
    print(f"Total chunks: {total_chunks}")
    print(f"Deduplicated chunks: {deduplicated_chunks}")
    print(f"Space savings: {(deduplicated_chunks / max(total_chunks, 1)) * 100:.1f}%")

def process_commit_smart(sha, commit_data, branches, depth, parsers, languages, 
                        commit_graph, chunker, commit_count):
    """Process a commit using smart chunking strategy"""
    
    # Get changed files
    changed_files = get_changed_files(sha)
    
    all_chunks = []
    
    for file_path in changed_files:
        # Determine language
        language = get_file_language(file_path, list(languages.keys()))
        if not language or language not in parsers:
            continue
        
        # Use smart chunking
        chunks = chunker.chunk_with_deduplication(
            sha, file_path, parsers[language], language, 
            commit_graph, commit_count
        )
        
        # Add commit metadata to all chunks
        for chunk in chunks:
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
        
        all_chunks.extend(chunks)
    
    return all_chunks

# Enhanced query function that can reconstruct files
def query_with_reconstruction(index, query, query_type="semantic"):
    """Query with ability to reconstruct full files when needed"""
    
    if query_type == "semantic":
        # Regular semantic search
        # Generate embedding for query
        from embeddings import generate_embeddings
        query_embedding = generate_embeddings([{"content": query, "type": "query"}])[0]['embedding']
        
        results = index.query(
            vector=query_embedding,
            top_k=10,
            include_metadata=True
        )
        
        # Check if any results are incremental diffs
        for match in results.matches:
            if match.metadata.get('storage_type') == 'incremental':
                # Need to reconstruct the full context
                from reconstruction import FileReconstructor
                with open("commit_graph.json", "r") as f:
                    data = json.load(f)
                
                reconstructor = FileReconstructor(index, data['graph'], data['repo_path'])
                full_content = reconstructor.reconstruct_file_at_sha(
                    match.metadata['sha'], 
                    match.metadata['path']
                )
                # Add reconstructed content to result
                match.metadata['reconstructed_content'] = full_content
        
        return results
    
    elif query_type == "historical":
        # Query for historical changes
        # This would search through diffs
        pass

if __name__ == "__main__":
    ingest_repository_with_smart_chunking()
