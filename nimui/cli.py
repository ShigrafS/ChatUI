import os
import sys
import argparse
import requests
from dotenv import load_dotenv

from nimui.model_manager import get_current_model, set_model, list_models


def handle_model_cmd(args):
    """Handle `chat model` subcommand."""
    if args.list:
        list_models()
    elif args.switch:
        set_model(args.switch)
    else:
        # just show current model
        current = get_current_model()
        print(f"Current model: {current}")


def handle_prompt_cmd(args):
    """Handle regular `chat <prompt>` usage."""
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
        "temperature": 0.2
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "accept": "application/json",
        "content-type": "application/json"
    }

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()

    answer = response.json()["choices"][0]["message"]["content"]
    print(answer)


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
            "--list", "-l", action="store_true",
            help="List all available models"
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