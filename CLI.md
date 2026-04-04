# NimUI CLI Guide

NimUI is a command-line interface for interacting with NVIDIA's hosted LLM models.

## Basic Chat

Interaction with the active model and general usage.

| Command | Description |
|---|---|
| `chat "How are you?"` | Sends a direct text prompt to the active model. |
| `chat -f / --file prompt.txt` | Reads the prompt content from a file and sends it. |
| `chat` | Enters interactive mode (stdin) if no prompt is provided. |

## Model Management

Commands for switching and exploring the 199+ available models.

| Command | Description |
|---|---|
| `chat model` | Shows the currently active model. |
| `chat model -l / --list` | Lists all available model groups (llm, multimodal, etc.) with model counts. |
| `chat model -l <group>` | Lists all models within the specific category. |
| `chat model -l all` | Dumps every single supported model into the terminal. |
| `chat model --search <term>` | Fuzzy search across all 199 models (e.g., `chat model --search llama`). |
| `chat model -s / --s <name>` | Switches the active model. Supports partial names (e.g. `-s deepseek`). |

## Configuration

Your preferences are stored locally at:
- **Windows**: `%USERPROFILE%\.nimui\config.json`
- **Linux/macOS**: `~/.nimui/config.json`

The **default model** is `meta/llama-3.1-70b-instruct`.
