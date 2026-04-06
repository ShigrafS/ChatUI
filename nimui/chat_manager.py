import sqlite3
import uuid
from pathlib import Path
from nimui.model_manager import get_config_dir, load_config, save_config

DB_NAME = "chats.db"

def _get_db_path():
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / DB_NAME

def _get_conn():
    """Create a SQLite connection with foreign keys and WAL mode enabled."""
    conn = sqlite3.connect(_get_db_path())
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn

def _init_db():
    """Initialize SQLite database with chats and messages tables."""
    with _get_conn() as conn:
        cursor = conn.cursor()
        
        # Chats table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                model TEXT NOT NULL,
                workspace_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE SET NULL
            )
        """)
        
        # Messages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
            )
        """)

        # Workspaces table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workspaces (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                root_path TEXT UNIQUE NOT NULL,
                status TEXT DEFAULT 'indexed',
                files_count INTEGER DEFAULT 0,
                chunk_size INTEGER DEFAULT 100,
                chunk_overlap INTEGER DEFAULT 10,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Workspace Files table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workspace_files (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                rel_path TEXT NOT NULL,
                size_bytes INTEGER,
                last_modified TIMESTAMP,
                FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE
            )
        """)

        # Workspace Chunks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workspace_chunks (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                file_id TEXT NOT NULL,
                start_line INTEGER,
                end_line INTEGER,
                content TEXT NOT NULL,
                language TEXT,
                vector_id INTEGER,
                FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE,
                FOREIGN KEY (file_id) REFERENCES workspace_files (id) ON DELETE CASCADE
            )
        """)

        # Virtual table for Full-Text Search (FTS5)
        # We store the workspace_id and chunk_id for filtering
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                content,
                workspace_id UNINDEXED,
                chunk_id UNINDEXED
            )
        """)

        # Workspace Symbols table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workspace_symbols (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                file_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                chunk_id TEXT,
                name TEXT NOT NULL,
                type TEXT,
                language TEXT,
                start_line INTEGER,
                end_line INTEGER,
                signature TEXT,
                FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE,
                FOREIGN KEY (file_id) REFERENCES workspace_files (id) ON DELETE CASCADE,
                FOREIGN KEY (chunk_id) REFERENCES workspace_chunks (id) ON DELETE SET NULL
            )
        """)

        # Tasks table for planning
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                goal TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
            )
        """)

        # Task Steps table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_steps (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                description TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                file_path TEXT,
                FOREIGN KEY (task_id) REFERENCES tasks (id) ON DELETE CASCADE
            )
        """)
        
        conn.commit()

def create_chat(title, model):
    """Create a new chat session."""
    _init_db()
    chat_id = str(uuid.uuid4())
    with _get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chats (id, title, model) VALUES (?, ?, ?)",
            (chat_id, title, model)
        )
        conn.commit()
    
    # Set as current chat
    set_current_chat(chat_id)
    return chat_id

def list_chats(search=None):
    """List all chat sessions, optionally filtered by title."""
    _init_db()
    with _get_conn() as conn:
        cursor = conn.cursor()
        if search:
            cursor.execute(
                "SELECT id, title, model, updated_at FROM chats WHERE title LIKE ? ORDER BY updated_at DESC",
                (f"%{search}%",)
            )
        else:
            cursor.execute("SELECT id, title, model, updated_at FROM chats ORDER BY updated_at DESC")
            
        rows = cursor.fetchall()
        return [{"id": r[0], "title": r[1], "model": r[2], "updated_at": r[3]} for r in rows]

def get_chat_history(chat_id):
    """Retrieve full message history for a chat session."""
    _init_db()
    with _get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY timestamp ASC, id ASC",
            (chat_id,)
        )
        rows = cursor.fetchall()
        return [{"role": r[0], "content": r[1]} for r in rows]

def add_message(chat_id, role, content):
    """Add a message to a chat session and update its timestamp."""
    _init_db()
    with _get_conn() as conn:
        cursor = conn.cursor()
        # 1. Add message
        cursor.execute(
            "INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
            (chat_id, role, content)
        )
        # 2. Update chat timestamp
        cursor.execute(
            "UPDATE chats SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (chat_id,)
        )
        conn.commit()

def delete_chat(chat_id):
    """Delete a chat session and its history."""
    _init_db()
    with _get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        conn.commit()
    
    # If the current chat was deleted, clear it or pick most recent
    cfg = load_config()
    if cfg.get("current_chat_id") == chat_id:
        with _get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM chats ORDER BY updated_at DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                cfg["current_chat_id"] = row[0]
            else:
                del cfg["current_chat_id"]
            save_config(cfg)

def rename_chat(chat_id, new_title):
    """Update title of a chat session."""
    _init_db()
    with _get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE chats SET title = ? WHERE id = ?",
            (new_title, chat_id)
        )
        conn.commit()

def get_current_chat_id():
    """Retrieve active chat ID from config."""
    cfg = load_config()
    return cfg.get("current_chat_id")

def set_current_chat(chat_id):
    """Update active chat ID in config."""
    cfg = load_config()
    cfg["current_chat_id"] = chat_id
    save_config(cfg)

def get_chat_by_partial(term):
    """Find a chat by partial ID or title match."""
    _init_db()
    with _get_conn() as conn:
        cursor = conn.cursor()
        
        # Try ID first (exact)
        cursor.execute("SELECT id, title FROM chats WHERE id = ?", (term,))
        row = cursor.fetchone()
        if row:
            return [{"id": row[0], "title": row[1]}]
            
        # Try title or ID partial match
        cursor.execute(
            "SELECT id, title FROM chats WHERE title LIKE ? OR id LIKE ? ORDER BY updated_at DESC",
            (f"%{term}%", f"%{term}%")
        )
        rows = cursor.fetchall()
        return [{"id": r[0], "title": r[1]} for r in rows]

# Task & Planning Helpers

def create_task_with_steps(chat_id: str, goal: str, steps: List[Dict]):
    """Store a generated plan as a task with ordered steps."""
    _init_db()
    task_id = str(uuid.uuid4())
    with _get_conn() as conn:
        cursor = conn.cursor()
        # 1. Close any existing active tasks for this chat
        cursor.execute("UPDATE tasks SET status = 'completed' WHERE chat_id = ? AND status = 'active'", (chat_id,))
        
        # 2. Create the new task
        cursor.execute("INSERT INTO tasks (id, chat_id, goal) VALUES (?, ?, ?)", (task_id, chat_id, goal))
        
        # 3. Insert steps
        for i, s in enumerate(steps):
            step_id = str(uuid.uuid4())
            cursor.execute(
                "INSERT INTO task_steps (id, task_id, step_index, description, file_path) VALUES (?, ?, ?, ?, ?)",
                (step_id, task_id, i+1, s['description'], s.get('file_path'))
            )
        conn.commit()
    return task_id

def get_active_task(chat_id: str) -> Optional[Dict]:
    """Retrieve the current active task and its steps."""
    _init_db()
    with _get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, goal, created_at FROM tasks WHERE chat_id = ? AND status = 'active'", (chat_id,))
        row = cursor.fetchone()
        if not row:
            return None
        
        task = {"id": row[0], "goal": row[1], "created_at": row[2], "steps": []}
        cursor.execute("SELECT step_index, description, status, file_path FROM task_steps WHERE task_id = ? ORDER BY step_index", (task['id'],))
        for r in cursor.fetchall():
            task['steps'].append({
                "index": r[0], "description": r[1], "status": r[2], "file_path": r[3]
            })
        return task

def update_step_status(task_id: str, step_index: int, status: str = 'done'):
    """Update progress on a specific step."""
    _init_db()
    with _get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE task_steps SET status = ? WHERE task_id = ? AND step_index = ?", (status, task_id, step_index))
        conn.commit()
