import os
from pinecone import Pinecone, ServerlessSpec

def setup_vector_db():
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    
    index_name = "git-rag"
    existing_indexes = [index.name for index in pc.list_indexes()]
    
    if index_name not in existing_indexes:
        pc.create_index(
            name=index_name,
            dimension=1536,
            metric="cosine",
            spec=ServerlessSpec(
                cloud='aws',
                region='us-east-1'
            )
        )
    
    return pc.Index(index_name)

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
