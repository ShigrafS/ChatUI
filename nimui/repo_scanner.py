import os
import re
import logging
from pathlib import Path
from typing import List, Optional, Dict
import pathspec
from nimui.workspace_provider import (
    add_workspace_file, clear_workspace_files, update_workspace_stats,
    add_chunks_batch, get_workspace_by_path, add_symbols_batch, clear_workspace_symbols
)
from nimui import embedding_provider, vector_store

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
        clear_workspace_symbols(workspace_id)
        vector_store.delete_index(workspace_id)
        
        count = 0
        all_chunks = []
        all_symbols = []
        BATCH_SIZE = 50 # Lower batch size for API embedding limits
        
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
                    add_workspace_file(workspace_id, rel_path, stats.st_size, stats.st_mtime)
                    chunks = self.chunk_file(workspace_id, rel_path, full_path, chunk_size, overlap)
                    all_chunks.extend(chunks)
                    
                    # Extract symbols from file
                    syms = self.extract_symbols(workspace_id, rel_path, full_path)
                    all_symbols.extend(syms)
                    
                    if len(all_chunks) >= BATCH_SIZE:
                        self._flush_chunks(workspace_id, all_chunks)
                        all_chunks = []
                    
                    # Flush symbols periodically
                    if len(all_symbols) >= 200:
                        add_symbols_batch(workspace_id, all_symbols)
                        all_symbols = []
                        
                    count += 1
                except Exception as e:
                    logger.warning(f"Skipping {rel_path}: {e}")
                    continue

        if all_chunks:
            self._flush_chunks(workspace_id, all_chunks)
        
        # Final symbol flush
        if all_symbols:
            add_symbols_batch(workspace_id, all_symbols)
            
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

    # Regex patterns per language
    SYMBOL_PATTERNS = {
        'python': [
            (r'^(\s*)def\s+(\w+)\s*\(', 'function'),
            (r'^(\s*)class\s+(\w+)', 'class'),
        ],
        'javascript': [
            (r'function\s+(\w+)\s*\(', 'function'),
            (r'class\s+(\w+)', 'class'),
            (r'export\s+const\s+(\w+)', 'function'),
        ],
        'typescript': [
            (r'function\s+(\w+)\s*\(', 'function'),
            (r'class\s+(\w+)', 'class'),
            (r'interface\s+(\w+)', 'interface'),
            (r'export\s+const\s+(\w+)', 'function'),
        ],
    }

    # skip files bigger than 500KB or minified
    MAX_SYMBOL_FILE_SIZE = 500_000

    def extract_symbols(self, workspace_id: str, rel_path: str, full_path: Path) -> List[Dict]:
        """Extract function/class/interface definitions using regex."""
        ext = full_path.suffix.lower().lstrip('.')
        lang_map = {'py': 'python', 'js': 'javascript', 'ts': 'typescript', 'tsx': 'typescript'}
        language = lang_map.get(ext)
        if not language:
            return []

        patterns = self.SYMBOL_PATTERNS.get(language, [])
        if not patterns:
            return []

        # skip large / minified files
        try:
            size = full_path.stat().st_size
            if size > self.MAX_SYMBOL_FILE_SIZE:
                return []
        except OSError:
            return []

        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception:
            return []

        # basic minification check — avg line length > 200 likely minified
        if lines and (sum(len(l) for l in lines) / len(lines)) > 200:
            return []

        file_id = f"{workspace_id}:{rel_path}"
        symbols = []

        for line_no, line in enumerate(lines, start=1):
            # skip comment-only lines
            stripped = line.lstrip()
            if stripped.startswith('#') or stripped.startswith('//'):
                continue

            for pattern, sym_type in patterns:
                m = re.search(pattern, line)
                if m:
                    # last group is the name
                    name = m.group(m.lastindex)
                    # rough end_line: scan for next def/class or +50 lines
                    end_line = self._estimate_end_line(lines, line_no - 1, language)
                    signature = line.rstrip()

                    symbols.append({
                        'file_id': file_id,
                        'file_path': rel_path,
                        'name': name,
                        'type': sym_type,
                        'language': language,
                        'start_line': line_no,
                        'end_line': end_line,
                        'signature': signature,
                    })
                    break  # one match per line is enough

        return symbols

    def _estimate_end_line(self, lines: List[str], start_idx: int, language: str) -> int:
        """Rough heuristic to find the end of a symbol block."""
        # For python: look for next line with same or less indentation
        indent = len(lines[start_idx]) - len(lines[start_idx].lstrip())
        max_end = min(start_idx + 200, len(lines))  # cap at 200 lines

        for i in range(start_idx + 1, max_end):
            l = lines[i]
            if not l.strip():  # skip blank lines
                continue
            cur_indent = len(l) - len(l.lstrip())
            if cur_indent <= indent and l.strip():
                return i  # line before this one, 1-indexed
        return max_end

    def _flush_chunks(self, workspace_id: str, chunks: List[Dict]):
        """Generate embeddings and flush chunks to database."""
        if not chunks:
            return
        
        try:
            # 1. Generate embeddings for the batch
            contents = [c['content'] for c in chunks]
            embeddings = embedding_provider.get_embeddings(contents)
            
            # 2. Add to FAISS and get starting vector_id
            start_id = vector_store.add_to_index(workspace_id, embeddings)
            
            # 3. Augment chunks with vector IDs
            for i, c in enumerate(chunks):
                c['vector_id'] = start_id + i
                
        except Exception as e:
            logger.error(f"Failed to generate embeddings for batch: {e}")
            # we proceed anyway, but those chunks won't have vector search support
        
        # 4. Save to SQLite (includes vector_ids if successfully generated)
        add_chunks_batch(workspace_id, chunks)

def scan_repo(workspace_id: str, root_path: str) -> int:
    """Convenience helper to scan a repo."""
    scanner = Scanner(root_path)
    return scanner.scan(workspace_id)
