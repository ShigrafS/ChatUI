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
        cursor.execute("SELECT id, name, root_path, files_count FROM workspaces WHERE root_path = ?", (root_path,))
        row = cursor.fetchone()
        if row:
            return {"id": row[0], "name": row[1], "root_path": row[2], "files_count": row[3]}
    return None

def create_workspace(name: str, root_path: str) -> str:
    """Create a new workspace or return existing one."""
    _init_db()
    existing = get_workspace_by_path(root_path)
    if existing:
        return existing["id"]
    
    workspace_id = str(uuid.uuid4())
    with _get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO workspaces (id, name, root_path) VALUES (?, ?, ?)",
            (workspace_id, name, root_path)
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
    """Clear all files associated with a workspace before re-scanning."""
    _init_db()
    with _get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM workspace_files WHERE workspace_id = ?", (workspace_id,))
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
