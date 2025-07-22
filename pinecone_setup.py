import os
from pinecone import Pinecone, ServerlessSpec

def setup_vector_db():
    # New Pinecone client initialization
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    
    index_name = "git-rag"
    
    # Check if index exists
    if index_name not in [index.name for index in pc.list_indexes()]:
        pc.create_index(
            name=index_name,
            dimension=1536,  # OpenAI embedding dimension
            metric="cosine",
            spec=ServerlessSpec(
                cloud='aws',
                region='us-east-1'  # or your preferred region
            )
        )
    
    return pc.Index(index_name)

def upsert_embeddings(index, embeddings_with_metadata):
    """Batch upsert embeddings to Pinecone with metadata"""
    batch_size = 100  # Pinecone recommends 100 vectors per batch
    total_chunks = len(embeddings_with_metadata)
    successful_upserts = 0
    
    for i in range(0, total_chunks, batch_size):
        batch = embeddings_with_metadata[i:i+batch_size]
        
        vectors = []
        for chunk in batch:
            vector_id = f"{chunk['sha'][:8]}_{chunk['path']}_{chunk['line_start']}"
            vector_id = vector_id.replace('/', '_').replace('.', '_')
            
            vector_data = {
                'id': vector_id,
                'values': chunk['embedding'],
                'metadata': {
                    'sha': chunk['sha'],
                    'path': chunk['path'],
                    'language': chunk['language'],
                    'content': chunk['content'][:1000],  # Truncate for metadata limit
                    'line_start': chunk['line_start'],
                    'line_end': chunk['line_end'],
                    'type': chunk.get('type', 'code'),  # 'code' or 'diff'
                    'branches': chunk.get('branches', []),  # Add branch info
                    'timestamp': chunk.get('timestamp', ''),
                    'commit_message': chunk.get('commit_message', '')[:500]
                }
            }
            vectors.append(vector_data)
        
        try:
            index.upsert(vectors=vectors)
            successful_upserts += len(vectors)
            print(f"Upserted {successful_upserts}/{total_chunks} vectors...")
        except Exception as e:
            print(f"Error upserting batch {i//batch_size}: {e}")
    
    print(f"Successfully upserted {successful_upserts} vectors")
    return successful_upserts

def upsert_hybrid_embeddings(index, embeddings_with_metadata):
    """Upsert both dense and sparse embeddings for hybrid search"""
    for chunk in embeddings_with_metadata:
        vector_data = {
            'id': f"{chunk['sha'][:8]}_{chunk['path']}_{chunk['line_start']}",
            'values': chunk['embedding'],  # Dense embedding
            'sparse_values': chunk.get('sparse_embedding'),  # Optional sparse embedding
            'metadata': {...}
        }

def stream_upsert_embeddings(index, chunk_generator):
    """Stream upserts to handle large repositories efficiently"""
    batch = []
    for chunk in chunk_generator:
        batch.append(chunk)
        if len(batch) >= 100:
            upsert_embeddings(index, batch)
            batch = []
    
    # Don't forget the last batch
    if batch:
        upsert_embeddings(index, batch)


