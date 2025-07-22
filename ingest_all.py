import json
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Import your modules
from ingest_cli import build_parsers, get_language, get_file_language, chunk_file
from sha_parser import get_changed_files, get_file_at_sha, get_diff_for_file
from dag_utils import topological_sort, get_commit_depth, get_branches_containing_commit
from pinecone_setup import setup_vector_db
# from embeddings import generate_embeddings, upsert_embeddings

load_dotenv()

def ingest_repository():
    """Ingest entire repository into Pinecone"""
    print("🚀 Starting Git-RAG Repository Ingestion\n")
    
    # Load commit graph
    with open("commit_graph.json", "r") as f:
        data = json.load(f)
        commit_graph = data['graph']
        branch_tips = data['branch_tips']
        repo_path = data['repo_path']
    
    print(f"📁 Repository: {repo_path}")
    print(f"📊 Total commits: {len(commit_graph)}")
    print(f"🌳 Branches: {list(branch_tips.keys())}\n")
    
    # Get languages
    try:
        languages = get_language()
        print(f"🔤 Languages detected: {list(languages.keys()) if isinstance(languages, dict) else languages}")
    except Exception as e:
        print(f"⚠️  Could not fetch languages from GitHub API: {e}")
        languages = ['Python', 'JavaScript', 'TypeScript', 'Java', 'Go']
        print(f"🔤 Using fallback languages: {languages}")
    
    # Build parsers
    print("\n🔧 Building language parsers...")
    parsers = build_parsers(languages if isinstance(languages, list) else list(languages.keys()))
    if not parsers:
        print("❌ Failed to build any parsers. Exiting.")
        return
    
    # Set up Pinecone
    print("\n🔗 Setting up Pinecone...")
    try:
        index = setup_vector_db()
        print("✅ Pinecone index ready")
    except Exception as e:
        print(f"❌ Failed to setup Pinecone: {e}")
        print("Make sure PINECONE_API_KEY is set in .env")
        return
    
    # Process commits in topological order
    sorted_commits = topological_sort(commit_graph)
    print(f"\n📈 Processing {len(sorted_commits)} commits...")
    
    # Track statistics
    stats = {
        'total_commits': len(sorted_commits),
        'processed_commits': 0,
        'total_chunks': 0,
        'total_files': 0,
        'errors': 0,
        'start_time': datetime.now()
    }
    
    # Process in batches to handle large repos
    batch_size = 10  # Process 10 commits at a time
    
    for batch_start in range(0, len(sorted_commits), batch_size):
        batch_end = min(batch_start + batch_size, len(sorted_commits))
        batch_commits = sorted_commits[batch_start:batch_end]
        
        batch_chunks = []
        
        for sha in batch_commits:
            try:
                # Get commit metadata
                commit_data = commit_graph[sha]
                branches = get_branches_containing_commit(sha, commit_graph, branch_tips)
                depth = get_commit_depth(sha, commit_graph)
                
                # Process commit
                commit_chunks = process_commit(
                    sha, commit_data, branches, depth, 
                    parsers, languages, stats
                )
                
                batch_chunks.extend(commit_chunks)
                stats['processed_commits'] += 1
                
                # Progress update
                if stats['processed_commits'] % 10 == 0:
                    progress = (stats['processed_commits'] / stats['total_commits']) * 100
                    print(f"\n📊 Progress: {progress:.1f}% ({stats['processed_commits']}/{stats['total_commits']})")
                    print(f"   Chunks extracted: {stats['total_chunks']}")
                    print(f"   Files processed: {stats['total_files']}")
                
            except Exception as e:
                print(f"\n❌ Error processing commit {sha[:8]}: {e}")
                stats['errors'] += 1
                continue
        
        # Generate embeddings and upload batch
        # if batch_chunks:
        #     try:
        #         print(f"\n🤖 Generating embeddings for {len(batch_chunks)} chunks...")
        #         embedded_chunks = generate_embeddings(batch_chunks)
                
        #         print(f"📤 Uploading to Pinecone...")
        #         upsert_embeddings(index, embedded_chunks)
                
        #     except Exception as e:
        #         print(f"❌ Error uploading batch: {e}")
        #         stats['errors'] += 1
    
    # Final statistics
    elapsed = datetime.now() - stats['start_time']
    print("\n" + "="*60)
    print("✅ INGESTION COMPLETE!")
    print("="*60)
    print(f"📊 Final Statistics:")
    print(f"   Total commits processed: {stats['processed_commits']}")
    print(f"   Total chunks created: {stats['total_chunks']}")
    print(f"   Total files processed: {stats['total_files']}")
    print(f"   Errors encountered: {stats['errors']}")
    print(f"   Time elapsed: {elapsed}")
    print(f"   Average time per commit: {elapsed / max(stats['processed_commits'], 1)}")
    
    # Save statistics
    with open("ingestion_stats.json", "w") as f:
        json.dump({
            **stats,
            'start_time': stats['start_time'].isoformat(),
            'end_time': datetime.now().isoformat(),
            'elapsed_seconds': elapsed.total_seconds()
        }, f, indent=2)

def process_commit(sha, commit_data, branches, depth, parsers, languages, stats):
    """Process a single commit and extract chunks"""
    chunks = []
    
    # Get changed files
    changed_files = get_changed_files(sha)
    
    for file_path in changed_files:
        # Determine language
        language = get_file_language(
            file_path, 
            languages if isinstance(languages, list) else list(languages.keys())
        )
        
        if not language or language not in parsers:
            continue
        
        try:
            # Get file content
            content = get_file_at_sha(sha, file_path)
            if not content:
                continue
            
            # Extract code chunks
            file_chunks = chunk_file(sha, file_path, parsers[language], language)
            
            # Add metadata to each chunk
            for chunk in file_chunks:
                chunk.update({
                    'branches': branches,
                    'parents': commit_data['parents'],
                    'children': commit_data.get('children', []),
                    'depth': depth,
                    'is_merge': len(commit_data['parents']) > 1,
                    'refs': commit_data.get('refs', []),
                    'timestamp': commit_data['timestamp'],
                    'commit_message': commit_data['message'],
                    'author': commit_data['author']
                })
            
            chunks.extend(file_chunks)
            stats['total_files'] += 1
            
            # Also store the diff if not initial commit
            if commit_data['parents']:
                try:
                    diff = get_diff_for_file(sha, file_path)
                    if diff:
                        diff_chunk = {
                            'content': diff,
                            'sha': sha,
                            'path': file_path,
                            'type': 'diff',
                            'language': language,
                            'line_start': 0,
                            'line_end': 0,
                            'branches': branches,
                            'parents': commit_data['parents'],
                            'is_merge': len(commit_data['parents']) > 1,
                            'depth': depth,
                            'commit_message': commit_data['message'],
                            'timestamp': commit_data['timestamp']
                        }
                        chunks.append(diff_chunk)
                except:
                    pass  # Skip if diff fails
                    
        except Exception as e:
            print(f"   ⚠️  Error processing {file_path}: {e}")
            continue
    
    stats['total_chunks'] += len(chunks)
    return chunks

# def verify_ingestion(index):
#     """Verify the ingestion worked by running sample queries"""
#     print("\n🔍 Verifying ingestion...")
    
#     # Get index stats
#     stats = index.describe_index_stats()
#     print(f"✅ Total vectors in index: {stats['total_vector_count']}")
    
#     # Try a sample query
#     try:
#         from embeddings import generate_embeddings
        
#         # Create a test query
#         test_query = "authentication and login functions"
#         query_chunk = {'content': test_query, 'type': 'query'}
#         embedded_query = generate_embeddings([query_chunk])[0]
        
#         # Search
#         results = index.query(
#             vector=embedded_query['embedding'],
#             top_k=3,
#             include_metadata=True
#         )
        
#         print(f"\n🔍 Sample query: '{test_query}'")
#         print(f"Found {len(results.matches)} matches:")
        
#         for i, match in enumerate(results.matches):
#             print(f"\n{i+1}. Score: {match.score:.3f}")
#             print(f"   File: {match.metadata['path']}")
#             print(f"   SHA: {match.metadata['sha'][:8]}")
#             print(f"   Content preview: {match.metadata['content'][:100]}...")
            
#     except Exception as e:
#         print(f"⚠️  Could not run verification query: {e}")

if __name__ == "__main__":
    # Check for required environment variables
    required_vars = [os.getenv('OPENAI_API_KEY'), os.getenv('PINECONE_API_KEY')]
    missing = [var for var in required_vars if not var]

    if missing:
        print(f"❌ Missing required environment variables: {missing}")
        print("Please set them in your .env file")
    #     sys.exit(1)
    
    # Check if commit graph exists
    if not os.path.exists("commit_graph.json"):
        print("❌ commit_graph.json not found. Run script.py first!")
        sys.exit(1)
    
    # Run ingestion
    ingest_repository()
    
    # Verify it worked
    try:
        index = setup_vector_db()
        #verify_ingestion(index)
    except Exception as e:
        print(f"⚠️  Could not verify ingestion: {e}")
