# main.py
import os
import requests
from dotenv import load_dotenv

def main():
    load_dotenv()
    API_KEY = os.getenv("NVIDIA_API_KEY")
    if not API_KEY:
        raise ValueError("NVIDIA_API_KEY environment variable not set!")

    MODEL = "meta/llama-3.1-70b-instruct"

    def ask(prompt: str) -> str:
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
        return response.json()["choices"][0]["message"]["content"]

    result = ask("Explain recursion like I'm 10 years old")
    print(result)

if __name__ == "__main__":
    main()