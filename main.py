import os
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

load_dotenv

pc = pc(api_key=os.getenv('PINECONE_API_KEY'))