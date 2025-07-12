import openai

def generate_embeddings(chunks):
    openai.api_key = os.getenv("OPENAI_API_KEY")
    
    for chunk in chunks:
        # Use different models based on content type
        model = "text-embedding-3-large" if chunk.get('type') == 'code' else "text-embedding-3-small"
        
        response = openai.Embedding.create(
            model=model,
            input=chunk['content']
        )
        
        chunk['embedding'] = response['data'][0]['embedding']
    
    return chunks

def upsert_embeddings(index, embeddings_with_metadata):
    """Batch upsert embeddings to Pinecone with metadata"""
    batch_size = 100  # Pinecone recommends 100 vectors per batch
    total_chunks = len(embeddings_with_metadata)
    successful_upserts = 0
    
    for i in range(0, total_chunks, batch_size):
        batch = embeddings_with_metadata[i:i+batch_size]
        
        # Prepare vectors with unique IDs
        vectors = []
        for chunk in batch:
            # Create unique ID - crucial for avoiding overwrites
            vector_id = f"{chunk['sha'][:8]}_{chunk['path']}_{chunk['line_start']}"
            
            # Ensure ID is valid (alphanumeric, hyphens, underscores only)
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
            # Upsert to Pinecone
            index.upsert(vectors=vectors)
            successful_upserts += len(vectors)
            print(f"Upserted {successful_upserts}/{total_chunks} vectors...")
        except Exception as e:
            print(f"Error upserting batch {i//batch_size}: {e}")
            # Could implement retry logic here
    
    print(f"Successfully upserted {successful_upserts} vectors")
    return successful_upserts
