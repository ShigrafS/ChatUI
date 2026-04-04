import os
import sys
import argparse
import requests
from dotenv import load_dotenv

def main():
    load_dotenv()
    API_KEY = os.getenv("NVIDIA_API_KEY")
    if not API_KEY:
        print("Error: NVIDIA_API_KEY is not set in .env")
        sys.exit(1)

    MODEL = "meta/llama-3.1-70b-instruct"

    parser = argparse.ArgumentParser(description="Ask NVIDIA API a question.")
    parser.add_argument("prompt", nargs="?", help="Prompt text for the AI")
    parser.add_argument("--file", "-f", help="Read prompt from a file")

    args = parser.parse_args()

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

if __name__ == "__main__":
    main()