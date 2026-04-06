import uuid
from typing import Optional, List, Dict
from nimui.chat_manager import _get_conn, _init_db
from nimui.model_manager import load_config, save_config

def get_active_workspace_id() -> Optional[str]:
    """Retrieve the current active workspace ID from config."""
    cfg = load_config()
    return cfg.get("active_workspace_id")

def set_active_workspace_id(workspace_id: Optional[str]):
    """Set the current active workspace ID in config."""
    cfg = load_config()
    if workspace_id:
        cfg["active_workspace_id"] = workspace_id
    elif "active_workspace_id" in cfg:
        del cfg["active_workspace_id"]
    save_config(cfg)

def get_workspace_by_path(root_path: str) -> Optional[Dict]:
    """Find a workspace by its root path."""
    _init_db()
    with _get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, root_path, files_count, chunk_size, chunk_overlap FROM workspaces WHERE root_path = ?", (root_path,))
        row = cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "name": row[1],
                "root_path": row[2],
                "files_count": row[3],
                "chunk_size": row[4],
                "chunk_overlap": row[5]
            }
    return None

def create_workspace(name: str, root_path: str, chunk_size: int = 100, chunk_overlap: int = 10) -> str:
    """Create a new workspace or return existing one."""
    _init_db()
    existing = get_workspace_by_path(root_path)
    if existing:
        return existing["id"]
    
    workspace_id = str(uuid.uuid4())
    with _get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO workspaces (id, name, root_path, chunk_size, chunk_overlap) VALUES (?, ?, ?, ?, ?)",
            (workspace_id, name, root_path, chunk_size, chunk_overlap)
        )
        conn.commit()
    return workspace_id

def update_workspace_stats(workspace_id: str, files_count: int):
    """Update file count and indexing time."""
    _init_db()
    with _get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE workspaces SET files_count = ?, indexed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (files_count, workspace_id)
        )
        conn.commit()

def add_workspace_file(workspace_id: str, rel_path: str, size_bytes: int, last_modified: str):
    """Add or update a file record for a workspace."""
    _init_db()
    file_id = f"{workspace_id}:{rel_path}"
    with _get_conn() as conn:
        cursor = conn.cursor()
        # insert or replace for simplicity (Phase 0)
        cursor.execute(
            "INSERT OR REPLACE INTO workspace_files (id, workspace_id, rel_path, size_bytes, last_modified) VALUES (?, ?, ?, ?, ?)",
            (file_id, workspace_id, rel_path, size_bytes, last_modified)
        )
        conn.commit()

def clear_workspace_files(workspace_id: str):
    """Clear all files and chunks associated with a workspace before re-scanning."""
    _init_db()
    with _get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM workspace_files WHERE workspace_id = ?", (workspace_id,))
        cursor.execute("DELETE FROM workspace_chunks WHERE workspace_id = ?", (workspace_id,))
        cursor.execute("DELETE FROM chunks_fts WHERE workspace_id = ?", (workspace_id,))
        conn.commit()

def add_chunks_batch(workspace_id: str, chunks: List[Dict]):
    """Add a batch of chunks to storage and FTS index in a single transaction."""
    if not chunks:
        return
        
    _init_db()
    with _get_conn() as conn:
        cursor = conn.cursor()
        for i, c in enumerate(chunks):
            chunk_id = str(uuid.uuid4())
            file_id = f"{workspace_id}:{c['rel_path']}"
            
            # 1. Store in regular table (using provided vector_id if available)
            v_id = c.get('vector_id')
            cursor.execute(
                "INSERT INTO workspace_chunks (id, workspace_id, file_id, start_line, end_line, content, language, vector_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (chunk_id, workspace_id, file_id, c['start'], c['end'], c['content'], c.get('language'), v_id)
            )
            # 2. Store in FTS virtual table
            cursor.execute(
                "INSERT INTO chunks_fts (content, workspace_id, chunk_id) VALUES (?, ?, ?)",
                (c['content'], workspace_id, chunk_id)
            )
        conn.commit()

def add_chunk(workspace_id: str, file_rel_path: str, start_line: int, end_line: int, content: str, language: str = None):
    """Add a single code chunk (convenience wrapper)."""
    add_chunks_batch(workspace_id, [{
        'rel_path': file_rel_path,
        'start': start_line,
        'end': end_line,
        'content': content,
        'language': language
    }])

def search_chunks(workspace_id: str, query: str, limit: int = 15) -> List[Dict]:
    """Perform hybrid search (FTS5 + Vector) using RRF."""
    # 1. Get Keyword Results
    keyword_results = keyword_search(workspace_id, query, limit=limit*2)
    
    # 2. Get Vector Results (if possible)
    from nimui import embedding_provider, vector_store
    vector_results = []
    try:
        query_emb = embedding_provider.get_single_embedding(query)
        offsets, distances = vector_store.search_index(workspace_id, query_emb, top_k=limit*2)
        if offsets:
            vector_results = _get_chunks_by_vector_ids(workspace_id, offsets)
    except Exception as e:
        import logging
        logging.getLogger("nimui").warning(f"Vector search failed: {e}")

    # 3. Reciprocal Rank Fusion (RRF)
    # RRF score = sum( 1 / (60 + rank) )
    scores = {} # (file_id, start_line) -> score
    id_to_chunk = {}
    
    def rrf_merge(results, k=60):
        for rank, r in enumerate(results):
            key = (r['rel_path'], r['start_line'])
            if key not in scores:
                scores[key] = 0
                id_to_chunk[key] = r
            scores[key] += 1.0 / (k + rank + 1)

    rrf_merge(keyword_results)
    rrf_merge(vector_results)

    # Sort and take top N
    final_keys = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)[:limit]
    return [id_to_chunk[k] for k in final_keys]

def keyword_search(workspace_id: str, query: str, limit: int = 15) -> List[Dict]:
    """Search for relevant chunks using FTS5."""
    _init_db()
    
    # Sanitize: Remove special characters that crash FTS5
    import re
    safe_query = re.sub(r'[^\w\s]', ' ', query).strip()
    
    keywords = [w for w in safe_query.split() if len(w) > 2]
    if not keywords: keywords = safe_query.split()
    if not keywords: return []

    fts_match = " OR ".join([f"{kw}*" for kw in keywords])
    
    with _get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT wc.file_id, wc.start_line, wc.end_line, wc.content, f.rel_path, wc.language
                FROM workspace_chunks wc
                JOIN chunks_fts cf ON wc.id = cf.chunk_id
                JOIN workspace_files f ON wc.file_id = f.id
                WHERE cf.workspace_id = ? AND chunks_fts MATCH ?
                LIMIT ?
            """, (workspace_id, fts_match, limit))
        except Exception:
            return []
        
        rows = cursor.fetchall()
        return [{
            "file_id": r[0], "start_line": r[1], "end_line": r[2],
            "content": r[3], "rel_path": r[4], "language": r[5]
        } for r in rows]

def _get_chunks_by_vector_ids(workspace_id: str, vector_ids: List[int]) -> List[Dict]:
    """Retrieve chunks from SQLite by their FAISS vector IDs."""
    if not vector_ids: return []
    _init_db()
    
    # We need to maintain the order of vector_ids (for ranking)
    placeholders = ",".join(["?"] * len(vector_ids))
    with _get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT wc.file_id, wc.start_line, wc.end_line, wc.content, f.rel_path, wc.language, wc.vector_id
            FROM workspace_chunks wc
            JOIN workspace_files f ON wc.file_id = f.id
            WHERE wc.workspace_id = ? AND wc.vector_id IN ({placeholders})
        """, (workspace_id, *vector_ids))
        
        rows = cursor.fetchall()
        # Sort rows based on the original vector_ids order
        id_map = {r[6]: r for r in rows}
        sorted_rows = []
        for vid in vector_ids:
            if vid in id_map:
                sorted_rows.append(id_map[vid])
                
        return [{
            "file_id": r[0], "start_line": r[1], "end_line": r[2],
            "content": r[3], "rel_path": r[4], "language": r[5]
        } for r in sorted_rows]

def add_symbols_batch(workspace_id: str, symbols: List[Dict]):
    """Batch insert extracted symbols into workspace_symbols."""
    if not symbols:
        return
    _init_db()
    with _get_conn() as conn:
        cursor = conn.cursor()
        for s in symbols:
            sym_id = str(uuid.uuid4())
            cursor.execute(
                """INSERT INTO workspace_symbols
                   (id, workspace_id, file_id, file_path, chunk_id, name, type, language, start_line, end_line, signature)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sym_id, workspace_id, s['file_id'], s['file_path'], s.get('chunk_id'),
                 s['name'], s['type'], s.get('language'), s['start_line'], s.get('end_line'), s.get('signature'))
            )
        conn.commit()

def search_symbols(workspace_id: str, query: str, limit: int = 20) -> List[Dict]:
    """Search symbols by name using LIKE."""
    _init_db()
    with _get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name, type, file_path, start_line, end_line, signature, language
            FROM workspace_symbols
            WHERE workspace_id = ? AND name LIKE ?
            ORDER BY name
            LIMIT ?
        """, (workspace_id, f"%{query}%", limit))
        rows = cursor.fetchall()
        return [{
            "name": r[0], "type": r[1], "file_path": r[2],
            "start_line": r[3], "end_line": r[4],
            "signature": r[5], "language": r[6]
        } for r in rows]

def get_chunks_near_lines(workspace_id: str, file_path: str, start_line: int, end_line: int, window: int = 150) -> List[Dict]:
    """Retrieve chunks in the same file within a line window of the given range."""
    _init_db()
    with _get_conn() as conn:
        cursor = conn.cursor()
        # Find chunks that overlap with [start - window, end + window]
        # We also join with workspace_files to get the rel_path consistently
        cursor.execute("""
            SELECT wc.file_id, wc.start_line, wc.end_line, wc.content, f.rel_path, wc.language
            FROM workspace_chunks wc
            JOIN workspace_files f ON wc.file_id = f.id
            WHERE wc.workspace_id = ? 
              AND f.rel_path = ?
              AND wc.start_line <= ?
              AND wc.end_line >= ?
            ORDER BY wc.start_line
        """, (workspace_id, file_path, end_line + window, start_line - window))
        
        rows = cursor.fetchall()
        return [{
            "file_id": r[0], "start_line": r[1], "end_line": r[2],
            "content": r[3], "rel_path": r[4], "language": r[5]
        } for r in rows]

def clear_workspace_symbols(workspace_id: str):
    """Remove all symbols for a workspace (used during re-scan)."""
    _init_db()
    with _get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM workspace_symbols WHERE workspace_id = ?", (workspace_id,))
        conn.commit()

def get_workspace_files(workspace_id: str) -> List[str]:
    """List all file paths in a workspace."""
    _init_db()
    with _get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT rel_path FROM workspace_files WHERE workspace_id = ? ORDER BY rel_path", (workspace_id,))
        rows = cursor.fetchall()
        return [r[0] for r in rows]

def list_workspaces() -> List[Dict]:
    """List all available workspaces."""
    _init_db()
    with _get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, root_path, files_count FROM workspaces")
        rows = cursor.fetchall()
        return [{"id": r[0], "name": r[1], "root_path": r[2], "files_count": r[3]} for r in rows]
