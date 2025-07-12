import pinecone
import os

def setup_vector_db():
    pinecone.init(
        api_key=os.getenv("PINECONE_API_KEY"),
        environment=os.getenv("PINECONE_ENV")
    )
    
    # Create index if doesn't exist
    if "git-rag" not in pinecone.list_indexes():
        pinecone.create_index(
            "git-rag",
            dimension=1536,  # OpenAI embedding dimension
            metric="cosine"
        )
    
    return pinecone.Index("git-rag")

def upsert_embeddings(index, embeddings_with_metadata):
    # Batch upsert as specified (100 at a time)
    batch_size = 100
    for i in range(0, len(embeddings_with_metadata), batch_size):
        batch = embeddings_with_metadata[i:i+batch_size]
        
        vectors = [
            (
                f"{chunk['sha']}_{chunk['path']}_{chunk['line_start']}",
                chunk['embedding'],
                {
                    'sha': chunk['sha'],
                    'path': chunk['path'],
                    'language': chunk['language'],
                    'content': chunk['content'][:1000],  # Truncate for metadata
                    'line_start': chunk['line_start'],
                    'line_end': chunk['line_end']
                }
            )
            for chunk in batch
        ]
        
        index.upsert(vectors)
