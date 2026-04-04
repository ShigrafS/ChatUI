# main.py
import os
import sys
import requests
from dotenv import load_dotenv

def main():
    load_dotenv()
    API_KEY = os.getenv("NVIDIA_API_KEY")
    if not API_KEY:
        print("Error: NVIDIA_API_KEY is not set in .env")
        sys.exit(1)

    MODEL = "meta/llama-3.1-70b-instruct"

    if len(sys.argv) < 2:
        print("Usage: nimui <prompt>")
        sys.exit(1)

    prompt = " ".join(sys.argv[1:])

    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 500
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