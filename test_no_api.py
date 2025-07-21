import json
import numpy as np
import os
from dotenv import load_dotenv

# Import your modules
from ingest_cli import build_parsers, get_language, get_file_language, chunk_file
from sha_parser import get_changed_files, get_file_at_sha
from dag_utils import topological_sort, get_commit_depth, get_branches_containing_commit

load_dotenv()

def mock_generate_embeddings(chunks):
    """Generate fake embeddings for testing"""
    print(f"\n🤖 MOCK: Would generate embeddings for {len(chunks)} chunks")
    
    for chunk in chunks:
        # Generate a fake 1536-dimensional vector
        # Make it somewhat deterministic based on content
        seed = hash(chunk['content']) % 10000
        np.random.seed(seed)
        fake_embedding = np.random.randn(1536).tolist()
        
        chunk['embedding'] = fake_embedding
        
        print(f"\n📄 Chunk from {chunk['path']} (lines {chunk['line_start']}-{chunk['line_end']}):")
        print(f"   SHA: {chunk['sha'][:8]}")
        print(f"   Type: {chunk.get('type', 'code')}")
        print(f"   Language: {chunk.get('language', 'unknown')}")
        print(f"   Content preview (first 200 chars):")
        print("   " + "-" * 60)
        content_preview = chunk['content'][:200].replace('\n', '\n   ')
        print(f"   {content_preview}...")
        print("   " + "-" * 60)
        print(f"   Embedding: [{fake_embedding[0]:.4f}, {fake_embedding[1]:.4f}, ..., {fake_embedding[-1]:.4f}]")
        print(f"   Vector dimension: {len(fake_embedding)}")
    
    return chunks

def mock_upsert_embeddings(index, embeddings_with_metadata):
    """Mock the Pinecone upsert operation"""
    print(f"\n📊 MOCK: Would upsert {len(embeddings_with_metadata)} vectors to Pinecone")
    
    for i, chunk in enumerate(embeddings_with_metadata[:5]):  # Show first 5
        vector_id = f"{chunk['sha'][:8]}_{chunk['path']}_{chunk['line_start']}"
        vector_id = vector_id.replace('/', '_').replace('.', '_')
        
        print(f"\n🔑 Vector {i+1}:")
        print(f"   ID: {vector_id}")
        print(f"   Metadata:")
        print(f"     - SHA: {chunk['sha'][:8]}")
        print(f"     - Path: {chunk['path']}")
        print(f"     - Branches: {chunk.get('branches', [])}")
        print(f"     - Parents: {[p[:8] for p in chunk.get('parents', [])]}")
        print(f"     - Commit message: {chunk.get('commit_message', '')[:50]}...")
        print(f"     - Is merge: {chunk.get('is_merge', False)}")
        
    if len(embeddings_with_metadata) > 5:
        print(f"\n... and {len(embeddings_with_metadata) - 5} more vectors")

def test_single_commit():
    """Test processing a single commit without APIs"""
    print("🚀 Starting Git-RAG test without API keys\n")
    
    # Load commit graph
    with open("commit_graph.json", "r") as f:
        data = json.load(f)
        commit_graph = data['graph']
        branch_tips = data['branch_tips']
        repo_path = data['repo_path']
    
    print(f"📁 Repository: {repo_path}")
    print(f"📊 Total commits: {len(commit_graph)}")
    print(f"🌳 Branches: {list(branch_tips.keys())}\n")
    
    # Get languages (this might still need GitHub API token)
    try:
        languages = get_language()
        print(f"🔤 Languages detected: {list(languages.keys()) if isinstance(languages, dict) else languages}")
    except Exception as e:
        print(f"⚠️  Could not fetch languages from GitHub API: {e}")
        # Fallback to common languages
        languages = ['Python', 'JavaScript', 'Java', 'Go', 'C', 'C++']
        print(f"🔤 Using fallback languages: {languages}")
    
    # Pick a recent commit to test
    sorted_commits = topological_sort(commit_graph)
    test_sha = None
    for sha in sorted_commits:  # Not reversed!
        if commit_graph[sha]['parents']:  # Has parents = not initial commit
            test_sha = sha
            break

    if not test_sha:
        # If all else fails, just pick the first non-initial commit
        test_sha = sorted_commits[0] if sorted_commits else None

    if not test_sha:
        print("No suitable commit found for testing")
        return

    print(f"\n🔍 Testing with commit: {test_sha[:8]}")

    commit_data = commit_graph[test_sha]
    print(f"   Author: {commit_data['author']}")
    print(f"   Message: {commit_data['message']}")
    print(f"   Timestamp: {commit_data['timestamp']}")
    
    # Get commit context
    branches = get_branches_containing_commit(test_sha, commit_graph, branch_tips)
    depth = get_commit_depth(test_sha, commit_graph)
    
    print(f"   Branches: {branches}")
    print(f"   Depth: {depth}")
    print(f"   Parents: {[p[:8] for p in commit_data['parents']]}")
    
    # Get changed files
    changed_files = get_changed_files(test_sha)
    print(f"\n📝 Changed files: {len(changed_files)}")
    for f in changed_files[:5]:  # Show first 5
        print(f"   - {f}")
    if len(changed_files) > 5:
        print(f"   ... and {len(changed_files) - 5} more")
    
    # Try to parse one file
    print("\n🔧 Testing code parsing...")
    
    # Build parsers (this will fail if tree-sitter languages aren't downloaded)
    try:
        parsers = build_parsers(languages if isinstance(languages, list) else list(languages.keys()))
        print("✅ Parsers built successfully")
    except Exception as e:
        print(f"❌ Failed to build parsers: {e}")
        print("   Make sure to run: python setup_parsers.py")
        return
    
    # Process the first suitable file
    all_chunks = []
    for file_path in changed_files[:3]:  # Try first 3 files
        language = get_file_language(file_path, languages if isinstance(languages, list) else list(languages.keys()))
        
        if language and language in parsers:
            print(f"\n📄 Parsing {file_path} (Language: {language})")
            
            try:
                # Get file content
                content = get_file_at_sha(test_sha, file_path)
                if content:
                    print(f"   File size: {len(content)} bytes")
                    
                    # Extract chunks
                    chunks = chunk_file(test_sha, file_path, parsers[language], language)
                    print(f"   Extracted {len(chunks)} code chunks")
                    
                    # Add metadata
                    for chunk in chunks:
                        chunk.update({
                            'branches': branches,
                            'parents': commit_data['parents'],
                            'depth': depth,
                            'commit_message': commit_data['message'],
                            'timestamp': commit_data['timestamp']
                        })
                    
                    all_chunks.extend(chunks)
            except Exception as e:
                print(f"   Error processing file: {e}")
    
    if not all_chunks:
        print("\n⚠️  No chunks extracted. Make sure tree-sitter parsers are installed.")
        return
    
    # Mock embedding generation
    embedded_chunks = mock_generate_embeddings(all_chunks)
    
    # Mock vector storage
    mock_upsert_embeddings(None, embedded_chunks)
    
    print("\n✅ Test complete! This is what would be sent to OpenAI and Pinecone.")

def test_dag_traversal():
    """Test the DAG traversal logic"""
    print("\n🌳 Testing DAG traversal...")
    
    with open("commit_graph.json", "r") as f:
        data = json.load(f)
        commit_graph = data['graph']
    
    # Test topological sort
    sorted_commits = topological_sort(commit_graph)
    print(f"Topological sort produced {len(sorted_commits)} commits")
    print(f"First 5: {[s[:8] for s in sorted_commits[:5]]}")
    print(f"Last 5: {[s[:8] for s in sorted_commits[-5:]]}")
    
    # Test depth calculation
    depths = {}
    for sha in sorted_commits[:10]:
        depths[sha] = get_commit_depth(sha, commit_graph)
    
    print("\nCommit depths (first 10):")
    for sha, depth in depths.items():
        print(f"  {sha[:8]}: depth {depth}")

if __name__ == "__main__":
    # Make sure you've run script.py first to generate commit_graph.json
    if not os.path.exists("commit_graph.json"):
        print("❌ commit_graph.json not found. Run script.py first!")
        exit(1)
    
    test_single_commit()
    test_dag_traversal()
