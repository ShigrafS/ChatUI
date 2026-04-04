# NimUI CLI Guide

NimUI is a command-line interface for interacting with NVIDIA's hosted LLM models, now featuring **real-time streaming** for immediate feedback during chat.

## Basic Chat

Interaction with the active model and general usage.

| Command | Description |
|---|---|
| `chat "How are you?"` | Sends a direct text prompt to the active model. |
| `chat -f file.txt` | Reads a file and uses its content as the prompt. |
| `chat -f f1.txt -f f2.txt "Summarize"` | Combines multiple files with a text prompt for context. |
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
  
  ---
  
  ## Custom Aliases
  
  You can create your own command names to invoke NimUI. This is useful for short names (e.g. `n`) or handling frequent typos (e.g. `caht`).
  
  | Command | Description |
  |---|---|
  | `chat --alias <name>` | Registers `<name>` as a command. |
  
  Once registered, the alias works exactly like `chat`. To ensure these aliases work globally regardless of your active environment, you should add the following directory to your system's **PATH**:
  - **Windows**: `%USERPROFILE%\.nimui\scripts`
  - **Linux/macOS**: `~/.nimui/bin`
  
  Example usage after setup:
  ```bash
  chat --alias ai
  ai "Hello"
  ```
