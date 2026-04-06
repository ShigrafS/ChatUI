import os
from pathlib import Path
from typing import List, Set, Optional
import pathspec
from nimui.workspace_provider import add_workspace_file, clear_workspace_files, update_workspace_stats

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
        clear_workspace_files(workspace_id)
        
        count = 0
        for root, dirs, files in os.walk(self.root_path):
            rel_dir = os.path.relpath(root, self.root_path)
            
            # Filter directories in-place to prevent os.walk from descending
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
                    add_workspace_file(
                        workspace_id,
                        rel_path,
                        stats.st_size,
                        stats.st_mtime
                    )
                    count += 1
                except (OSError, PermissionError):
                    # Skip files that can't be accessed
                    continue
        
        update_workspace_stats(workspace_id, count)
        return count

def scan_repo(workspace_id: str, root_path: str) -> int:
    """Convenience helper to scan a repo."""
    scanner = Scanner(root_path)
    return scanner.scan(workspace_id)
