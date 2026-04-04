import os
import sys
import json
import argparse
import requests
from dotenv import load_dotenv

from nimui.model_manager import get_current_model, set_model, list_models, search_models


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

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            prompt = f.read()
    elif args.prompt:
        prompt = args.prompt
    else:
        # fallback to stdin
        print("Enter your prompt (Ctrl+Z then Enter to end):")
        prompt = sys.stdin.read()

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
        prompt_parser.add_argument("--file", "-f", help="Read prompt from a file")
        args = prompt_parser.parse_args()
        handle_prompt_cmd(args)


if __name__ == "__main__":
    main()