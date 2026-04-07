import json
import os
import requests
from typing import List, Dict
from nimui import retriever, chat_manager, workspace_provider
from nimui.model_manager import get_current_model

def generate_plan(chat_id: str, workspace_id: str, goal: str) -> List[Dict]:
    """
    Generate a step-by-step implementation plan for a given goal.
    Returns a list of steps with 'description' and optional 'file_path'.
    """
    # 1. Retrieve context
    context = retriever.retrieve_context(workspace_id, goal, top_n=10)
    
    # 2. Extract symbols for grounding
    symbols = workspace_provider.search_symbols(workspace_id, goal, limit=10)
    symbol_str = "\n".join([f"- {s['name']} ({s['type']}) in {s['file_path']}" for s in symbols])

    # 3. Build Prompt
    system_prompt = (
        "You are an expert AI software architect. "
        "Your task is to break down a high-level feature request into exactly 3-7 actionable steps. "
        "For each step, specify the file that needs to be modified if known.\n\n"
        "Return the plan ONLY as a JSON list of objects with 'description' and 'file_path' keys. "
        "Example output: [{\"description\": \"Add x\", \"file_path\": \"y.py\"}]\n\n"
        "CONTEXT:\n"
        f"{context}\n\n"
        "SYMBOLS FOUND:\n"
        f"{symbol_str}"
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Plan for: {goal}"}
    ]

    # 4. Call NVIDIA API
    MODEL = get_current_model()
    API_KEY = os.getenv("NVIDIA_API_KEY")
    if not API_KEY:
        raise ValueError("NVIDIA_API_KEY not set")

    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 1024,
        "stream": False # Use non-blocking for internal structured data
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "accept": "application/json",
        "content-type": "application/json"
    }

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    
    content = response.json()['choices'][0]['message']['content']
    
    # Strip markdown if present
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()
    
    try:
        steps = json.loads(content)
        # 5. Store in DB
        chat_manager.create_task_with_steps(chat_id, goal, steps)
        return steps
    except Exception as e:
        print(f"Error parsing plan JSON: {e}")
        print(f"Raw content: {content}")
        return []
