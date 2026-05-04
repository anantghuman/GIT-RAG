import os
import time
from pinecone import Pinecone, ServerlessSpec

EMBEDDING_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


def setup_vector_db():
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise RuntimeError("PINECONE_API_KEY is not set")

    pc = Pinecone(api_key=api_key)

    index_name = os.getenv("PINECONE_INDEX_NAME", "git-rag-index")
    model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    dimension = EMBEDDING_DIMENSIONS.get(model, 1536)
    cloud = os.getenv("PINECONE_CLOUD", "aws")
    region = os.getenv("PINECONE_REGION", "us-east-1")

    existing = [idx.name for idx in pc.list_indexes()]
    if index_name not in existing:
        print(f"Creating Pinecone index '{index_name}' (dim={dimension}, {cloud}/{region})")
        pc.create_index(
            name=index_name,
            dimension=dimension,
            metric="cosine",
            spec=ServerlessSpec(cloud=cloud, region=region),
        )
        # Wait for the index to be ready
        while not pc.describe_index(index_name).status.get("ready", False):
            time.sleep(1)

    return pc.Index(index_name)
