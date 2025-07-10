import os
from dotenv import load_dotenv
import subprocess, os, json, sys

load_dotenv()

# pc = pc(api_key=os.getenv('PINECONE_API_KEY'))

repo_url = os.getenv('REPO_NAME')

with open('shas,txt', 'r') as f:
    shas = f.read().splitlines()
# for sha in shas:
    