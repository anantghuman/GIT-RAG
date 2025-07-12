import subprocess, os, json, sys

from ingest_cli import build_parsers, get_language, get_file_language, chunk_file
from sha_parser import get_changed_files, get_commit_info, get_branches_for_sha, get_file_at_sha, get_diff_for_file
from embeddings import generate_embeddings, upsert_embeddings
from pinecone_setup import setup_vector_db
from dotenv import load_dotenv

load_dotenv()

def ingest_repository():
    # Read SHAs from your generated file
    with open("shas.txt", "r") as f:
        shas = f.read().strip().split('\n')
    
    # Get languages and build parsers
    languages = get_language()
    parsers = build_parsers(languages)
    
    # Set up vector DB
    index = setup_vector_db()
    
    # Process each SHA
    for sha in shas:
        # Get changed files for this SHA
        files = get_changed_files(sha)
        
        all_chunks = []
        for file_path in files:
            # Determine language from file extension
            language = get_file_language(file_path, languages)
            if language and language in parsers:
                chunks = chunk_file(sha, file_path, parsers[language], language)
                all_chunks.extend(chunks)
        
        # Generate embeddings and store
        if all_chunks:
            embedded_chunks = generate_embeddings(all_chunks)
            upsert_embeddings(index, embedded_chunks)


def process_commit(sha):
    # Get branch context
    branches = get_branches_for_sha(sha)
    
    # Get commit metadata
    commit_info = get_commit_info(sha)  # author, date, message
    
    # Get changed files
    changed_files = get_changed_files(sha)
    
    chunks = []
    
    for file_path in changed_files:
        # 1. Store the FULL file content at this SHA
        full_content = get_file_at_sha(sha, file_path)
        if full_content:
            # Parse and chunk the entire file
            file_chunks = chunk_file(full_content, file_path, sha)
            for chunk in file_chunks:
                chunk['branches'] = branches  # Add branch context
            chunks.extend(file_chunks)
        
        # 2. Also store the DIFF as a separate chunk
        diff = get_diff_for_file(sha, file_path)
        diff_chunk = {
            'type': 'diff',
            'content': diff,
            'sha': sha,
            'path': file_path,
            'branches': branches,
            'commit_message': commit_info['message']
        }
        chunks.append(diff_chunk)
    
    return chunks

    