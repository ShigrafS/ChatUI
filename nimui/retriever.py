from typing import List, Dict
from nimui.workspace_provider import search_chunks, search_symbols, get_chunks_near_lines

def retrieve_context(workspace_id: str, query: str, top_n: int = 8) -> str:
    """Fetch relevant code context, prioritizing logical flow over raw similarity."""
    results = retrieve_logic_flow(workspace_id, query, limit=top_n)
    
    if not results:
        return ""

    context_parts = []
    # Deduplicate results if any overlap occurred during expansion
    seen = set()
    for r in results:
        key = (r['rel_path'], r['start_line'])
        if key in seen:
            continue
        seen.add(key)
        
        header = f"[file: {r['rel_path']} | lines {r['start_line']}–{r['end_line']} | language: {r.get('language', 'unknown')}]"
        context_parts.append(f"{header}\n{r['content']}")
    
    return "\n\n".join(context_parts)

def retrieve_logic_flow(workspace_id: str, query: str, limit: int = 8) -> List[Dict]:
    """
    Experimental: Find symbols mentioned in query and expand context around them.
    Falls back to hybrid search if no symbols identified.
    """
    # 1. Identity symbols in the query (very basic: split by non-word)
    import re
    words = re.findall(r'\w+', query)
    potential_symbols = [w for w in words if len(w) > 3]
    
    found_symbols = []
    for sym_name in potential_symbols:
        # Exact match or very close
        syms = search_symbols(workspace_id, sym_name, limit=3)
        found_symbols.extend(syms)

    if not found_symbols:
        return search_chunks(workspace_id, query, limit=limit)

    # 2. Expand context for each symbol found
    expanded_results = []
    for s in found_symbols:
        # Get chunks in the neighborhood of the symbol definition
        # Window of 150 lines around the symbol
        proximity_chunks = get_chunks_near_lines(
            workspace_id, 
            s['file_path'], 
            s['start_line'], 
            s['end_line'] or s['start_line'], 
            window=150
        )
        expanded_results.extend(proximity_chunks)
        
        # If we have space, also look for "import" symbols in the same file to show dependencies
        # (This is a simplified "logic flow")
        if len(expanded_results) < limit:
            import_syms = search_symbols(workspace_id, f"import", limit=5) # This isn't quite right, needs more logic
            # For now, let's stick to proximity as it's the most reliable "flow" indicator
            pass

    # 3. If we don't have enough results, pad with hybrid search
    if len(expanded_results) < limit / 2:
        expanded_results.extend(search_chunks(workspace_id, query, limit=limit))

    return expanded_results[:limit]

def build_qa_prompt(query: str, context: str) -> List[Dict]:
    """Construct the messages for a grounded Q&A session."""
    system_prompt = (
        "You are an expert AI software engineer assistant.\n"
        "You have access to relevant code snippets from the repository provided below.\n"
        "Your task is to answer the user's question accurately using ONLY the provided context.\n"
        "Always cite specific files and line numbers in your explanation.\n"
        "If the context doesn't contain the answer, say you don't know based on the current indexing.\n\n"
        "CONTEXT:\n"
        f"{context}"
    )
    
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Question: {query}"}
    ]
