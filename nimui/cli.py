import os
import sys
import json
import argparse
import requests
from dotenv import load_dotenv

import platform
from pathlib import Path
from nimui.model_manager import get_current_model, set_model, list_models, search_models, add_alias, get_config_dir


def handle_model_cmd(args):
    """Handle `chat model` subcommand."""
    if args.list is not None:
        # --list was passed, could be empty string (no group) or a group name
        group = args.list if args.list else None
        list_models(group)
    elif args.search:
        search_models(args.search)
    elif args.switch:
        set_model(args.switch)
    else:
        current = get_current_model()
        print(f"Current model: {current}")


def handle_prompt_cmd(args):
    """Handle regular `chat <prompt>` usage with real-time streaming."""
    load_dotenv()
    API_KEY = os.getenv("NVIDIA_API_KEY")
    if not API_KEY:
        print("Error: NVIDIA_API_KEY is not set in .env")
        sys.exit(1)

    MODEL = get_current_model()

    parts = []

    # load file(s) if provided
    if args.file:
        for fpath in args.file:
            if not os.path.exists(fpath):
                print(f"Error: File not found: {fpath}")
                sys.exit(1)
            with open(fpath, "r", encoding="utf-8") as f:
                fname = os.path.basename(fpath)
                parts.append(f"--- FILE: {fname} ---\n{f.read()}")

    # append text prompt if given
    if args.prompt:
        parts.append(args.prompt)

    if not parts:
        # fallback to stdin
        print("Enter your prompt (Ctrl+Z then Enter to end):")
        parts.append(sys.stdin.read())

    prompt = "\n\n".join(parts)

    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "stream": True  # Enable SSE streaming
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "accept": "application/json",
        "content-type": "application/json"
    }

    try:
        with requests.post(url, json=payload, headers=headers, stream=True) as response:
            response.raise_for_status()
            
            # Simple "Thinking..." indicator
            print("Thinking...", end="\r", flush=True)
            first_chunk = True
            
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                    
                if line.startswith("data: "):
                    line = line[len("data: "):]
                
                if line.strip() == "[DONE]":
                    break
                    
                try:
                    data = json.loads(line)
                    if "choices" in data and len(data["choices"]) > 0:
                        content = data["choices"][0].get("delta", {}).get("content", "")
                        if content:
                            if first_chunk:
                                # clear the "Thinking..." line
                                print(" " * 12, end="\r", flush=True)
                                first_chunk = False
                            print(content, end="", flush=True)
                except json.JSONDecodeError:
                    # sometimes the API might send malformed chunk or partial
                    continue
            print() # newline at end
    except Exception as e:
        print(f"\nError connecting to API: {e}")
        sys.exit(1)


def handle_alias(alias_name):
    """Handle adding a command alias in a neutral location."""
    if not alias_name:
        print("Error: Please provide a name for the alias (e.g. `chat --alias ai`)")
        return

    # 1. Update config
    success = add_alias(alias_name)
    if not success:
        print(f"Alias '{alias_name}' already exists or is reserved.")
        return

    # 2. Determine neutral storage location
    config_dir = get_config_dir()
    if platform.system() == "Windows":
        target_dir = config_dir / "scripts"
        shim_name = f"{alias_name}.bat"
        content = f"@echo off\nchat %*\n"
    else:
        target_dir = config_dir / "bin"
        shim_name = alias_name
        content = f'#!/bin/bash\nchat "$@"\n'

    # 3. Create the directory and shim
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        shim_path = target_dir / shim_name
        
        with open(shim_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        if platform.system() != "Windows":
            os.chmod(shim_path, 0o755)

        print(f"\nSuccessfully created alias '{alias_name}' at: {shim_path}")
        print("-" * 50)
        print("IMPORTANT: To use this alias globally, please add this folder to your PATH:")
        print(f"  {target_dir}")
        print("-" * 50)
        print("Once added, restarts might be required for changes to take effect.")
        
    except Exception as e:
        print(f"Warning: Failed to create shim at {target_dir}. Alias added to config.")
        print(f"Error: {e}")


def main():
    # peek at argv to decide which path we're on
    # can't use subparsers — they eat the first positional arg
    # so `chat "some prompt"` breaks if "model" is a subcommand
    if len(sys.argv) > 1 and sys.argv[1] == "model":
        model_parser = argparse.ArgumentParser(
            prog="chat model",
            description="View or switch the active model."
        )
        model_parser.add_argument(
            "--s", "-s", dest="switch", metavar="MODEL_NAME",
            help="Switch to a different model"
        )
        model_parser.add_argument(
            "--list", "-l", nargs="?", const="", default=None,
            metavar="GROUP",
            help="List model groups, or models in a specific group"
        )
        model_parser.add_argument(
            "--search", metavar="TERM",
            help="Search for models by name"
        )
        args = model_parser.parse_args(sys.argv[2:])
        handle_model_cmd(args)
    else:
        prompt_parser = argparse.ArgumentParser(
            description="NimUI — chat with NVIDIA API models."
        )
        prompt_parser.add_argument("prompt", nargs="?", help="Prompt text for the AI")
        prompt_parser.add_argument("--file", "-f", action="append", help="File(s) to include as context (can use multiple times)")
        prompt_parser.add_argument("--alias", metavar="NAME", help="Create a custom command alias (e.g. `caht`, `ai`)")
        args = prompt_parser.parse_args()

        if args.alias:
            handle_alias(args.alias)
        else:
            handle_prompt_cmd(args)


if __name__ == "__main__":
    main()