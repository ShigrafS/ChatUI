import os
import requests
from typing import List, Dict, Optional
from nimui import workspace_provider, chat_manager, retriever
from nimui.model_manager import get_current_model

def analyze_step_impact(workspace_id: str, chat_id: str, step_index: int) -> Dict:
    """
    Perform impact analysis for a specific task step.
    Returns details on affected files, risk levels, and logic branches.
    """
    task = chat_manager.get_active_task(chat_id)
    if not task:
        return {"error": "No active task found"}
    
    step = next((s for s in task['steps'] if s['index'] == step_index), None)
    if not step:
        return {"error": f"Step {step_index} not found"}
    
    target_file = step.get('file_path')
    if not target_file:
        return {"error": "Step has no associated file path"}

    # 1. Trace dependents in the symbol graph
    dependents = workspace_provider.get_dependents(workspace_id, target_file)
    
    # 2. Get symbol definitions in target for grounding
    # (We find what else is in this file that might be touched)
    local_symbols = workspace_provider.search_symbols(workspace_id, "", limit=100)
    local_symbols = [s for s in local_symbols if s['file_path'] == target_file]

    # 3. Assess impact with LLM
    MODEL = get_current_model()
    API_KEY = os.getenv("NVIDIA_API_KEY")
    
    dependent_list = "\n".join([f"- {d['dependent_file']} imports it as: {d['signature']}" for d in dependents])
    symbol_list = "\n".join([f"- {s['name']} ({s['type']})" for s in local_symbols])

    system_prompt = (
        "You are a Change Impact Analyzer. "
        "Your goal is to predict regressions and dependency issues for a planned code change.\n\n"
        "Input context includes:\n"
        "1. The target file being modified.\n"
        "2. The description of the change.\n"
        "3. A list of files that IMPORT the target file.\n"
        "4. Symbols already existing in the target file.\n\n"
        "Your task:\n"
        "- Identify WHICH files are at risk.\n"
        "- Assess risk level (High: signature change/breaking; Medium: behavioral change; Low: refactor).\n"
        "- Suggest 1-2 manual verification or test cases.\n\n"
        "Output as JSON with keys: 'affected_files', 'risk_assessment', 'suggestions'."
    )
    
    user_prompt = (
        f"Target File: {target_file}\n"
        f"Proposed Change: {step['description']}\n\n"
        f"DEPENDENT FILES FOUND:\n{dependent_list}\n\n"
        f"LOCAL SYMBOLS:\n{symbol_list}"
    )

    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"}
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "accept": "application/json",
        "content-type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        return {"error": f"LLM analysis failed: {e}", "dependents": dependents}
