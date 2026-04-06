import os
import numpy as np
import faiss
from pathlib import Path
from typing import List, Tuple, Optional

# Index storage location
# C:\Users\user\.nimui\indices\<workspace_id>.faiss
def _get_index_path(workspace_id: str) -> Path:
    base_dir = Path.home() / ".nimui" / "indices"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / f"{workspace_id}.faiss"

def create_index(dimension: int = 4096):
    """Create a new L2 FAISS index."""
    return faiss.IndexFlatL2(dimension)

def save_index(index, workspace_id: str):
    """Save FAISS index to disk."""
    path = _get_index_path(workspace_id)
    faiss.write_index(index, str(path))

def load_index(workspace_id: str):
    """Load FAISS index from disk."""
    path = _get_index_path(workspace_id)
    if not path.exists():
        return None
    return faiss.read_index(str(path))
    
def delete_index(workspace_id: str):
    """Delete the FAISS index file for a workspace."""
    path = _get_index_path(workspace_id)
    if path.exists():
        path.unlink()

def add_to_index(workspace_id: str, embeddings: List[List[float]]):
    """Add multiple embeddings to a workspace index."""
    if not embeddings:
        return
    
    dim = len(embeddings[0])
    idx = load_index(workspace_id)
    if idx is None:
        idx = create_index(dim)
    
    # Check if dimension matches
    if idx.d != dim:
        # If dimension mismatch (rare, but possible if model changed)
        # For now, just reset the index to the new dimension
        idx = create_index(dim)
        
    embeddings_np = np.array(embeddings).astype('float32')
    start_id = idx.ntotal
    idx.add(embeddings_np)
    save_index(idx, workspace_id)
    return start_id

def search_index(workspace_id: str, query_embedding: List[float], top_k: int = 10) -> Tuple[List[int], List[float]]:
    """Search for top K nearest neighbors."""
    idx = load_index(workspace_id)
    if idx is None:
        return [], []
    
    query_np = np.array([query_embedding]).astype('float32')
    distances, offsets = idx.search(query_np, top_k)
    
    # distances are squared L2 distances
    # offsets are indices into the FAISS index (0, 1, 2...)
    return offsets[0].tolist(), distances[0].tolist()
