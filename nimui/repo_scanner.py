import os
import logging
from pathlib import Path
from typing import List, Optional, Dict
import pathspec
from nimui.workspace_provider import add_workspace_file, clear_workspace_files, update_workspace_stats, add_chunks_batch, get_workspace_by_path

# Basic logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nimui.scanner")

class Scanner:
    def __init__(self, root_path: str):
        self.root_path = Path(root_path).resolve()
        self.spec = self._load_ignore_specs()

    def _load_ignore_specs(self) -> pathspec.PathSpec:
        """Load ignore patterns from .gitignore and .chatignore."""
        patterns = []
        
        # 1. Load .gitignore
        gitignore = self.root_path / ".gitignore"
        if gitignore.exists():
            with open(gitignore, "r", encoding="utf-8") as f:
                patterns.extend(f.readlines())
        
        # 2. Load .chatignore
        chatignore = self.root_path / ".chatignore"
        if chatignore.exists():
            with open(chatignore, "r", encoding="utf-8") as f:
                patterns.extend(f.readlines())
        
        return pathspec.PathSpec.from_lines("gitwildmatch", patterns)

    def scan(self, workspace_id: str) -> int:
        """Scan directory and sync with database."""
        # 0. Get workspace config
        ws = get_workspace_by_path(str(self.root_path))
        chunk_size = ws["chunk_size"] if ws else 100
        overlap = ws["chunk_overlap"] if ws else 10
        
        clear_workspace_files(workspace_id)
        
        count = 0
        all_chunks = []
        BATCH_SIZE = 500 # chunks per batch flush
        
        for root, dirs, files in os.walk(self.root_path):
            rel_dir = os.path.relpath(root, self.root_path)
            
            # Filter directories in-place
            if rel_dir == ".":
                dirs[:] = [d for d in dirs if not self.spec.match_file(d)]
            else:
                dirs[:] = [d for d in dirs if not self.spec.match_file(os.path.join(rel_dir, d))]

            for file in files:
                rel_path = os.path.join(rel_dir, file) if rel_dir != "." else file
                
                if self.spec.match_file(rel_path):
                    continue
                
                full_path = Path(root) / file
                try:
                    stats = full_path.stat()
                    # 1. Add file record
                    add_workspace_file(
                        workspace_id,
                        rel_path,
                        stats.st_size,
                        stats.st_mtime
                    )
                    
                    # 2. Collect chunks
                    chunks = self.chunk_file(workspace_id, rel_path, full_path, chunk_size, overlap)
                    all_chunks.extend(chunks)
                    
                    # 3. Batch flush
                    if len(all_chunks) >= BATCH_SIZE:
                        add_chunks_batch(workspace_id, all_chunks)
                        all_chunks = []
                        
                    count += 1
                except (OSError, PermissionError, UnicodeDecodeError) as e:
                    logger.warning(f"Skipping {rel_path}: {e}")
                    continue
        
        # Final flush
        if all_chunks:
            add_chunks_batch(workspace_id, all_chunks)
            
        update_workspace_stats(workspace_id, count)
        return count

    def chunk_file(self, workspace_id: str, rel_path: str, full_path: Path, chunk_size: int, overlap: int) -> List[Dict]:
        """Read a file and return a list of chunks with overlap."""
        ext = full_path.suffix.lower().lstrip(".")
        # Mapping extension to language name
        lang_map = {
            'py': 'python', 'js': 'javascript', 'ts': 'typescript', 'java': 'java',
            'cpp': 'cpp', 'c': 'c', 'h': 'c', 'hpp': 'cpp', 'go': 'go', 'rs': 'rust',
            'rb': 'ruby', 'php': 'php', 'html': 'html', 'css': 'css', 'md': 'markdown',
            'json': 'json', 'yaml': 'yaml', 'yml': 'yaml', 'toml': 'toml', 'sh': 'shell'
        }
        language = lang_map.get(ext, ext)
        
        try:
            # Use errors="ignore" to avoid UnicodeDecodeError on files with mixed/bad encoding
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception as e:
            logger.warning(f"Could not read {rel_path}: {e}")
            return []

        if not lines:
            return []

        file_chunks = []
        total_lines = len(lines)
        start = 0
        while start < total_lines:
            end = min(start + chunk_size, total_lines)
            chunk_content = "".join(lines[start:end])
            
            file_chunks.append({
                'rel_path': rel_path,
                'start': start + 1,
                'end': end,
                'content': chunk_content,
                'language': language
            })
            
            step = max(1, chunk_size - overlap)
            start += step
            
            if end == total_lines:
                break
        
        return file_chunks

def scan_repo(workspace_id: str, root_path: str) -> int:
    """Convenience helper to scan a repo."""
    scanner = Scanner(root_path)
    return scanner.scan(workspace_id)
