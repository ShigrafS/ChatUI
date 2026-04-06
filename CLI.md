# NimUI CLI Guide

NimUI is a powerful command-line interface for interacting with NVIDIA's hosted LLM models, featuring **real-time streaming** and **persistent chat history**.

## Basic Chat

Quickly interact with the active model. If no active chat session exists, NimUI automatically creates a "Default Chat" and maintains history (last 20 messages).

| Command | Description |
|---|---|
| `chat "How are you?"` | Sends a prompt to the active model. |
| `chat -f file.txt` | Uses file content as the prompt. |
| `chat -f f1.txt -f f2.txt "Summarize"` | Combines multiple files for context. |
| `chat` | Enters interactive mode (stdin) if no prompt is provided. |
| `chat --alias <name>` | Registers a custom command name (e.g. `chat --alias ai`). |

---

## Chat Sessions

Manage persistent multi-turn conversations using the `chat chat` subcommand.

| Command | Description |
|---|---|
| `chat chat` | Shows a summary of the current active session. |
| `chat chat --list [term]` | Lists all sessions or searches by title/ID. |
| `chat chat --new "Title"` | Starts a brand new chat session with a custom title. |
| `chat chat --switch <id>` | Switches the active session (supports partial IDs or titles). |
| `chat chat --rename "New"` | Renames the current active session. |
| `chat chat --delete <id>` | Deletes a session and its history. |

---

## Model Management

Explore and switch between the 199+ available NVIDIA hosted models using the `chat model` subcommand.

| Command | Description |
|---|---|
| `chat model` | Displays the currently active model. |
| `chat model --list` | Lists all available model groups (llm, multimodal, etc.). |
| `chat model --list <group>` | Lists all models within a specific category. |
| `chat model --list all` | Dumps every supported model into the terminal. |
| `chat model --search <term>` | Fuzzy search across the entire model registry. |
| `chat model --s <name>` | Switches the active model (supports partial name matching). |

---

## Workspace & Engineering

NimUI features **Structure-Aware Hybrid RAG** and **Plan-to-Code** workflows. It indexes your repository locally to provide grounded answers and 1-click implementations.

| Command | Description |
|---|---|
| `chat attach --pwd` | Indexes the current directory (supports `.gitignore` and `.chatignore`). |
| `chat attach --dir <path>` | Indexes a specific directory path. |
| `chat attach ... --chunk-size 100` | Optional: Set custom chunk size for indexing. |
| `chat detach` | Removes the active workspace from the current session. |
| `chat status` | Shows active workspace info and current task/plan progress. |
| `chat tree` | Displays a visual file tree of the indexed workspace. |
| `chat symbols <query>` | Searches the structural symbol graph (functions, classes, imports). |
| `chat search <query>` | Full-text search across all indexed files (Hybrid Vector + FTS5). |
| `chat ask "How to X?"` | Grounded Q&A using your codebase as context. |
| `chat plan "Goal"` | Decomposes a high-level feature request into actionable steps. |
| `chat impact <n>` | Predicts regressions and downstream dependencies for plan step `<n>`. |
| `chat implement <n>` | Generates a minimalist unified diff to address plan step `<n>`. |
| `chat safe-implement <n>` | Runs impact analysis first, then implements if you confirm. |
| `chat next` | Automatically handles the next pending step in your active plan. |

---

## Configuration & Path Setup

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
