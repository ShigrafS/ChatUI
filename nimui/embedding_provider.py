import os
import requests
from typing import List, Optional
from dotenv import load_dotenv

def get_embeddings(texts: List[str], model: str = "nvidia/nv-embed-v1") -> List[List[float]]:
    """Generate embeddings for a list of strings using NVIDIA's API."""
    load_dotenv()
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise ValueError("NVIDIA_API_KEY not found in environment or .env")

    url = "https://integrate.api.nvidia.com/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    # We should handle batching if texts are too many, but let's start simple
    # The API usually supports up to some number of inputs
    payload = {
        "model": model,
        "input": texts,
        "encoding_format": "float"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        # Extract embeddings from response
        # NVIDIA follows OpenAI format: data: [{embedding: [...], index: 0}, ...]
        embeddings = [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]
        return embeddings
    except Exception as e:
        # print(f"Error generating embeddings: {e}")
        raise

def get_single_embedding(text: str, model: str = "nvidia/nv-embed-v1") -> List[float]:
    """Convenience for one string."""
    embeddings = get_embeddings([text], model)
    return embeddings[0]
