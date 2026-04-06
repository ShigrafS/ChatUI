from typing import List, Dict
from nimui.workspace_provider import search_chunks

def retrieve_context(workspace_id: str, query: str, top_n: int = 8) -> str:
    """Fetch relevant chunks and format as context for LLM."""
    results = search_chunks(workspace_id, query, limit=top_n)
    
    if not results:
        return ""

    context_parts = []
    for r in results:
        # Standardized Context Formatting
        header = f"[file: {r['rel_path']} | lines {r['start_line']}–{r['end_line']} | language: {r.get('language', 'unknown')}]"
        context_parts.append(f"{header}\n{r['content']}")
    
    return "\n\n".join(context_parts)

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
