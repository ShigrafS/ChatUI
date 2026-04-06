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
        for c in chunks:
            chunk_id = str(uuid.uuid4())
            file_id = f"{workspace_id}:{c['rel_path']}"
            
            # 1. Store in regular table
            cursor.execute(
                "INSERT INTO workspace_chunks (id, workspace_id, file_id, start_line, end_line, content, language) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (chunk_id, workspace_id, file_id, c['start'], c['end'], c['content'], c.get('language'))
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
    """Search for relevant chunks using FTS5."""
    _init_db()
    
    # 1. Sanitize: Remove special characters that crash FTS5
    import re
    # Keep alphanumeric, spaces, and some common chars like underscore
    safe_query = re.sub(r'[^\w\s]', ' ', query).strip()
    
    # 2. Split into words: FTS5 works best when matching keywords
    # We join words with " OR " or just space for better recall
    keywords = [w for w in safe_query.split() if len(w) > 2]
    if not keywords:
        # Fallback for short words if no long ones
        keywords = safe_query.split()
    
    # If no keywords at all, return empty
    if not keywords:
        return []

    # Construction of a query like: "word1* OR word2* OR word3*"
    # This matches if ANY word is present as a prefix, which is great for "streaming" matching "_stream_nvidia..."
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
        except sqlite3.OperationalError as e:
            logger.warning(f"FTS5 syntax fail for '{fts_match}': {e}. Retrying simple match.")
            # Fallback for potential syntax error (e.g. if query still has issues)
            # Try a simple "one of the words" match?
            simple_q = " OR ".join(keywords[:3])
            try:
                cursor.execute("""
                    SELECT wc.file_id, wc.start_line, wc.end_line, wc.content, f.rel_path, wc.language
                    FROM workspace_chunks wc
                    JOIN chunks_fts cf ON wc.id = cf.chunk_id
                    JOIN workspace_files f ON wc.file_id = f.id
                    WHERE cf.workspace_id = ? AND chunks_fts MATCH ?
                    LIMIT ?
                """, (workspace_id, simple_q, limit))
            except sqlite3.OperationalError:
                return []
        
        rows = cursor.fetchall()
        # Filter duplicates if JOIN + OR caused any? (Unlikely with LIMIT and JOIN on unique ids)
        return [{
            "file_id": r[0],
            "start_line": r[1],
            "end_line": r[2],
            "content": r[3],
            "rel_path": r[4],
            "language": r[5]
        } for r in rows]

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
