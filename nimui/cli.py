import os
import sys
import json
import argparse
import requests
from dotenv import load_dotenv

import platform
from pathlib import Path
from nimui.model_manager import get_current_model, set_model, list_models, search_models, add_alias, get_config_dir
from nimui import chat_manager


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
    
    # 1. Get or create current chat
    chat_id = chat_manager.get_current_chat_id()
    if not chat_id:
        chat_id = chat_manager.create_chat("Default Chat", MODEL)
        print(f"Created new default chat session: {chat_id[:8]}")
    
    # 2. Get history (cap at last 20 messages to protect context window)
    history = chat_manager.get_chat_history(chat_id)
    if len(history) > 20:
        history = history[-20:]

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

    # 3. Add prompt to state
    chat_manager.add_message(chat_id, "user", prompt)
    history.append({"role": "user", "content": prompt})

    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    payload = {
        "model": MODEL,
        "messages": history,
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
            full_response = ""
            
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
                            full_response += content
                except json.JSONDecodeError:
                    # sometimes the API might send malformed chunk or partial
                    continue
            print() # newline at end
            
            # 4. Save response to history
            if full_response:
                chat_manager.add_message(chat_id, "assistant", full_response)
    except Exception as e:
        print(f"\nError connecting to API: {e}")
        sys.exit(1)


def handle_chat_cmd(args):
    if args.list is not None:
        search_term = args.list if args.list else None
        chats = chat_manager.list_chats(search=search_term)
        current = chat_manager.get_current_chat_id()
        
        if not chats:
            print("No chat sessions found.")
            return
            
        print("\nYour Chat Sessions:\n")
        for c in chats:
            marker = " (active)" if c["id"] == current else ""
            print(f"  [{c['id'][:8]}] {c['title']:<30} ({c['model']}){marker}")
        print("\nUse `chat chat --switch <id-or-title>` to change.\n")
        
    elif args.new:
        chat_id = chat_manager.create_chat(args.new, get_current_model())
        print(f"Started new chat: {args.new} ({chat_id[:8]})")
        
    elif args.switch:
        matches = chat_manager.get_chat_by_partial(args.switch)
        if not matches:
            print(f"No chat found matching '{args.switch}'.")
        elif len(matches) == 1:
            chat_manager.set_current_chat(matches[0]["id"])
            print(f"Switched to: {matches[0]['title']} ({matches[0]['id'][:8]})")
        else:
            print(f"Multiple matches found for '{args.switch}':")
            for m in matches:
                print(f"  - [{m['id'][:8]}] {m['title']}")
            print("\nPlease use a more specific ID or title.")
            
    elif args.rename:
        current = chat_manager.get_current_chat_id()
        if not current:
            print("Error: No active chat to rename.")
            return
        chat_manager.rename_chat(current, args.rename)
        print(f"Chat renamed to: {args.rename}")
        
    elif args.delete:
        # use same matching logic for delete
        matches = chat_manager.get_chat_by_partial(args.delete)
        if not matches:
            print(f"No chat found matching '{args.delete}'.")
        elif len(matches) == 1:
            chat_manager.delete_chat(matches[0]["id"])
            print(f"Deleted chat: {matches[0]['title']}")
        else:
            print(f"Multiple matches found for '{args.delete}':")
            for m in matches:
                print(f"  - [{m['id'][:8]}] {m['title']}")
            print("\nPlease use a more specific ID or title to delete.")
    
    else:
        # summary of current chat
        current_id = chat_manager.get_current_chat_id()
        if not current_id:
            print("No active chat session. Send a prompt to start one.")
        else:
            # fetch its info
            chats = chat_manager.list_chats()
            current = next((c for c in chats if c["id"] == current_id), None)
            if current:
                print(f"Current Chat: {current['title']} ({current['id'][:8]})")
            else:
                print("Error: Active chat not found in storage.")


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
    elif len(sys.argv) > 1 and sys.argv[1] == "chat":
        chat_parser = argparse.ArgumentParser(
            prog="chat chat",
            description="Manage your chat sessions and history."
        )
        group = chat_parser.add_mutually_exclusive_group()
        group.add_argument("--new", "-n", metavar="TITLE", help="Start a new chat session")
        group.add_argument("--list", "-l", nargs="?", const="", default=None, metavar="SEARCH", help="List or search chat sessions")
        group.add_argument("--switch", "-s", metavar="ID_OR_TITLE", help="Switch active chat session")
        group.add_argument("--rename", "-r", metavar="TITLE", help="Rename the current session")
        group.add_argument("--delete", "-d", metavar="ID_OR_TITLE", help="Delete a chat session")
        
        args = chat_parser.parse_args(sys.argv[2:])
        handle_chat_cmd(args)
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