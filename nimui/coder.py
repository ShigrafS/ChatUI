import os
import requests
from typing import Optional
from nimui import retriever, workspace_provider
from nimui.model_manager import get_current_model

def generate_diff(workspace_id: str, step_description: str, file_path: Optional[str] = None) -> str:
    """
    Generate a unified diff for a specific implementation step.
    """
    # 1. Retrieve context for the step
    # We query by description + file_path to pin the right area
    query = f"{step_description} in {file_path}" if file_path else step_description
    context = retriever.retrieve_context(workspace_id, query, top_n=8)

    # 2. Build the Diff-focused Prompt
    MODEL = get_current_model()
    
    system_prompt = (
        "You are an expert AI software engineer. "
        "Your task is to provide a minimalist, correct UNIFIED DIFF for the requested change. "
        "Only output the diff itself. Do not provide explanations. "
        "Use correctly formatted hunks (@@ -L,count +L,count @@). "
        "Base your changes on the provided repository context.\n\n"
        "CONTEXT:\n"
        f"{context}"
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Implement this step: {step_description}"}
    ]

    # 3. Call NVIDIA API
    API_KEY = os.getenv("NVIDIA_API_KEY")
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.05, # Low temperature for precise code
        "max_tokens": 2048,
        "stream": False
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "accept": "application/json",
        "content-type": "application/json"
    }

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    
    diff = response.json()['choices'][0]['message']['content']
    
    # Simple cleanup to remove markdown code fences if model adds them
    if "```diff" in diff:
        diff = diff.split("```diff")[1].split("```")[0].strip()
    elif "```" in diff:
        diff = diff.split("```")[1].split("```")[0].strip()
        
    return diff
