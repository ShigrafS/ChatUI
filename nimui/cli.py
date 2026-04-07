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
from nimui import workspace_provider
from nimui import repo_scanner
from nimui import retriever
from nimui import planner
from nimui import coder
from nimui import impact
from rich.console import Console
from rich.tree import Tree
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

console = Console()


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

    _stream_nvidia_response(MODEL, history, chat_id)


def _stream_nvidia_response(model, messages, chat_id=None):
    """Internal helper to handle streaming from NIM API."""
    load_dotenv()
    API_KEY = os.getenv("NVIDIA_API_KEY")
    if not API_KEY:
        print("Error: NVIDIA_API_KEY is not set in .env")
        sys.exit(1)

    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "stream": True
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "accept": "application/json",
        "content-type": "application/json"
    }

    try:
        with requests.post(url, json=payload, headers=headers, stream=True) as response:
            if response.status_code == 404:
                rprint(f"[red]Error:[/red] Model '{model}' not found or API key invalid.")
                return
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
                    continue
            print() # newline at end
            
            # Save response to history if we have a chat_id
            if chat_id and full_response:
                chat_manager.add_message(chat_id, "assistant", full_response)
    except Exception as e:
        print(f"\nError connecting to API: {e}")
        # sys.exit(1) # don't exit entirely in multi-command mode


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


def handle_attach_cmd(args):
    """Handle `chat attach` subcommand."""
    target_path = None
    if args.pwd:
        target_path = os.getcwd()
    elif args.dir:
        target_path = os.path.abspath(args.dir)
    
    if not target_path:
        print("Error: Specify --pwd or --dir <path>")
        return

    if not os.path.isdir(target_path):
        print(f"Error: Not a directory: {target_path}")
        return

    name = os.path.basename(target_path) or "root"
    
    chunk_size = getattr(args, 'chunk_size', 100) or 100
    overlap = getattr(args, 'overlap', 10) or 10

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description=f"Attaching {target_path} (chunk_size={chunk_size}, overlap={overlap})...", total=None)
        
        # 1. Create/Get workspace
        ws_id = workspace_provider.create_workspace(name, target_path, chunk_size=chunk_size, chunk_overlap=overlap)
        
        # 2. Scan repo
        count = repo_scanner.scan_repo(ws_id, target_path)
        
        # 3. Set as active
        workspace_provider.set_active_workspace_id(ws_id)

    rprint(f"[green]Successfully attached workspace:[/green] {name}")
    rprint(f"Path: {target_path}")
    rprint(f"Files indexed: {count}")
    rprint(f"Config: chunk_size={chunk_size}, overlap={overlap}")


def handle_status_cmd():
    """Handle `chat status` command."""
    ws_id = workspace_provider.get_active_workspace_id()
    if not ws_id:
        rprint("[yellow]No active workspace.[/yellow] Use `chat attach --pwd` to start.")
        return

    # find it in list (lazy way)
    workspaces = workspace_provider.list_workspaces()
    ws = next((w for w in workspaces if w["id"] == ws_id), None)
    
    if not ws:
        rprint("[red]Error:[/red] Active workspace not found in database.")
        return

    rprint(f"\n[bold]Current Workspace:[/bold] {ws['name']}")
    rprint(f"  ID:   {ws['id'][:8]}")
    rprint(f"  Path: {ws['root_path']}")
    rprint(f"  Files: {ws['files_count']}")
    
    # Task status
    chat_id = chat_manager.get_current_chat_id()
    if chat_id:
        task = chat_manager.get_active_task(chat_id)
        if task:
            rprint(f"\n[bold yellow]Active Task:[/bold yellow] {task['goal']}")
            for s in task['steps']:
                status = "[green]✔[/green]" if s['status'] == 'done' else "[grey]○[/grey]"
                rprint(f"  {status} {s['index']}. {s['description']}")
    print()


def handle_tree_cmd():
    """Handle `chat tree` command."""
    ws_id = workspace_provider.get_active_workspace_id()
    if not ws_id:
        rprint("[yellow]No active workspace.[/yellow]")
        return

    files = workspace_provider.get_workspace_files(ws_id)
    if not files:
        print("No files indexed in this workspace.")
        return

    # Build tree
    workspaces = workspace_provider.list_workspaces()
    ws = next((w for w in workspaces if w["id"] == ws_id), None)
    
    tree = Tree(f"[bold blue]{ws['name']}[/bold blue] ({ws['root_path']})")
    
    # Simple tree builder logic
    nodes = {"": tree}
    for rel_path in sorted(files):
        parts = rel_path.split(os.sep)
        current_path = ""
        for i, part in enumerate(parts):
            parent_path = current_path
            current_path = os.path.join(current_path, part) if current_path else part
            
            if current_path not in nodes:
                is_file = (i == len(parts) - 1)
                label = f"[green]{part}[/green]" if is_file else f"[bold yellow]{part}[/bold yellow]"
                nodes[current_path] = nodes[parent_path].add(label)
    
    console.print(tree)


def handle_detach_cmd():
    """Handle `chat detach` command."""
    workspace_provider.set_active_workspace_id(None)
    rprint("[green]Detached from workspace.[/green]")


def handle_search_cmd(query):
    """Handle `chat search` command."""
    ws_id = workspace_provider.get_active_workspace_id()
    if not ws_id:
        rprint("[yellow]No active workspace.[/yellow]")
        return

    results = workspace_provider.search_chunks(ws_id, query)
    if not results:
        rprint(f"[yellow]No results found for:[/yellow] {query}")
        return

    rprint(f"\n[bold green]Search results for '{query}':[/bold green]\n")
    for r in results:
        lang_str = f" [blue][{r['language']}][/blue]" if r.get('language') else ""
        rprint(f"[bold cyan]{r['rel_path']}[/bold cyan]{lang_str} [grey]({r['start_line']}-{r['end_line']})[/grey]")
        
        # Format the content snippet with a simple box or indentation
        lines = r['content'].splitlines()
        max_lines = 5
        snippet = "\n".join([f"  {line}" for line in lines[:max_lines]])
        print(f"{snippet}")
        if len(lines) > max_lines:
            print(f"  ...")
        print("-" * 30)


def handle_symbols_cmd(query):
    """Handle `chat symbols` command."""
    ws_id = workspace_provider.get_active_workspace_id()
    if not ws_id:
        rprint("[yellow]No active workspace.[/yellow]")
        return

    results = workspace_provider.search_symbols(ws_id, query)
    if not results:
        rprint(f"[yellow]No symbols found matching:[/yellow] {query}")
        return

    rprint(f"\n[bold green]Symbols matching '{query}':[/bold green]\n")
    for s in results:
        type_color = {"function": "cyan", "class": "magenta", "interface": "blue"}.get(s['type'], "white")
        line_range = f":{s['start_line']}"
        if s.get('end_line'):
            line_range += f"-{s['end_line']}"
        rprint(f"  [{type_color}]{s['name']}[/{type_color}] ({s['type']})")
        rprint(f"    {s['file_path']}{line_range}")
        if s.get('signature'):
            rprint(f"    [dim]{s['signature'].strip()}[/dim]")
        print()

        print()


def handle_plan_cmd(goal):
    """Handle `chat plan` command."""
    ws_id = workspace_provider.get_active_workspace_id()
    if not ws_id:
        rprint("[yellow]No active workspace.[/yellow]")
        return
    
    chat_id = chat_manager.get_current_chat_id()
    if not chat_id:
        # Auto-create chat for plan
        chat_id = chat_manager.create_chat(f"Plan: {goal}", get_current_model())

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description=f"Decomposing task: {goal}...", total=None)
        steps = planner.generate_plan(chat_id, ws_id, goal)
    
    if not steps:
        rprint("[red]Failed to generate plan. Check logs.[/red]")
        return

    rprint(f"\n[bold green]Implementation Plan for:[/bold green] {goal}")
    for i, s in enumerate(steps, 1):
        file_hint = f" [dim]({s.get('file_path')})[/dim]" if s.get('file_path') else ""
        rprint(f" [blue]{i}.[/blue] {s['description']}{file_hint}")
    rprint(f"\nUse [bold]chat implement <number>[/bold] or [bold]chat next[/bold] to proceed.")


def handle_implement_cmd(step_num):
    """Handle `chat implement <step_num>` command."""
    ws_id = workspace_provider.get_active_workspace_id()
    if not ws_id:
        rprint("[yellow]No active workspace.[/yellow]")
        return
    
    chat_id = chat_manager.get_current_chat_id()
    if not chat_id:
        rprint("[yellow]No active chat session.[/yellow]")
        return
    
    task = chat_manager.get_active_task(chat_id)
    if not task:
        rprint("[yellow]No active task to implement. Use `chat plan <goal>` first.[/yellow]")
        return
    
    try:
        step_idx = int(step_num)
        step = next((s for s in task['steps'] if s['index'] == step_idx), None)
    except ValueError:
        rprint(f"[red]Error:[/red] Invalid step number: {step_num}")
        return
    
    if not step:
        rprint(f"[red]Error:[/red] Step {step_num} not found in current plan.")
        return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description=f"Generating diff for step {step_num}: {step['description']}...", total=None)
        diff = coder.generate_diff(ws_id, step['description'], step['file_path'])
    
    if not diff:
        rprint("[red]Failed to generate diff.[/red]")
        return

    rprint(f"\n[bold green]Suggested Diff for Step {step_num}:[/bold green]\n")
    # Using simple print for diff to ensure it's easy to copy
    print(diff)
    print("\n" + "="*40)
    rprint("Apply this diff manually or with [bold]git apply[/bold].")
    rprint("Once applied, you can move to the next step with [bold]chat next[/bold].")
    
    # Mark as done for convenience
    chat_manager.update_step_status(task['id'], step['index'], 'done')


def handle_impact_cmd(step_num):
    """Handle `chat impact <step_num>` command."""
    ws_id = workspace_provider.get_active_workspace_id()
    if not ws_id:
        rprint("[yellow]No active workspace.[/yellow]")
        return
    
    chat_id = chat_manager.get_current_chat_id()
    if not chat_id:
        rprint("[yellow]No active chat session.[/yellow]")
        return
    
    try:
        step_idx = int(step_num)
    except ValueError:
        rprint(f"[red]Error:[/red] Invalid step number: {step_num}")
        return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description=f"Analyzing impact for step {step_num}...", total=None)
        result = impact.analyze_step_impact(ws_id, chat_id, step_idx)
    
    if isinstance(result, str):
        import json
        try:
            res = json.loads(result)
            rprint(f"\n[bold yellow]Impact Assessment for Step {step_num}:[/bold yellow]")
            
            rprint("\n[bold]Affected Files:[/bold]")
            for f in res.get('affected_files', []):
                rprint(f"  - {f}")
            
            rprint(f"\n[bold]Risk Assessment:[/bold] {res.get('risk_assessment', 'Unknown')}")
            
            rprint("\n[bold]Suggestions:[/bold]")
            for s in res.get('suggestions', []):
                rprint(f"  - {s}")
        except:
            rprint(f"\n[bold red]Error parsing impact report.[/bold red]")
            rprint(result)
    else:
        rprint(f"\n[bold red]Impact Analysis Failed:[/bold red] {result.get('error')}")


def handle_safe_implement_cmd(step_num):
    """Run impact analysis then implement."""
    handle_impact_cmd(step_num)
    rprint("\n[bold cyan]Proceed with implementation? (y/n)[/bold cyan]")
    choice = input("> ").lower()
    if choice == 'y':
        handle_implement_cmd(step_num)


def handle_next_cmd():
    """Find the first pending step and implement it."""
    chat_id = chat_manager.get_current_chat_id()
    if not chat_id:
        rprint("[yellow]No active session.[/yellow]")
        return
    
    task = chat_manager.get_active_task(chat_id)
    if not task or not task['steps']:
        rprint("[yellow]No active plan found.[/yellow]")
        return
    
    pending = [s for s in task['steps'] if s['status'] == 'pending']
    if not pending:
        rprint("[green]All steps in the current plan are marked as completed![/green]")
        return
    
    next_step = pending[0]
    handle_implement_cmd(next_step['index'])


def handle_ask_cmd(query):
    """Handle `chat ask` command (Grounded RAG)."""
    ws_id = workspace_provider.get_active_workspace_id()
    if not ws_id:
        rprint("[yellow]No active workspace.[/yellow] Attach one with `chat attach --pwd` first.")
        return

    MODEL = get_current_model()
    
    # 1. Retrieve context
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description=f"Searching repository for: {query}...", total=None)
        context = retriever.retrieve_context(ws_id, query)
    
    if not context:
        rprint("[yellow]No relevant code found in repository to answer your question.[/yellow]")
        return
    
    # 2. Build QA messages
    messages = retriever.build_qa_prompt(query, context)
    
    # 3. Stream from NVIDIA
    rprint(f"\n[bold green]Answer (using context from repository):[/bold green]\n")
    _stream_nvidia_response(MODEL, messages)


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
    elif len(sys.argv) > 1 and sys.argv[1] == "attach":
        attach_parser = argparse.ArgumentParser(prog="chat attach", description="Attach a repository to the current session.")
        group = attach_parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--pwd", action="store_true", help="Attach current directory")
        group.add_argument("--dir", metavar="PATH", help="Attach specific directory")
        attach_parser.add_argument("--chunk-size", type=int, help="Number of lines per chunk (default: 100)")
        attach_parser.add_argument("--overlap", type=int, help="Number of lines to overlap (default: 10)")
        args = attach_parser.parse_args(sys.argv[2:])
        handle_attach_cmd(args)
    elif len(sys.argv) > 1 and sys.argv[1] == "status":
        handle_status_cmd()
    elif len(sys.argv) > 1 and sys.argv[1] == "search":
        if len(sys.argv) < 3:
            print("Usage: chat search <query>")
            return
        handle_search_cmd(sys.argv[2])
    elif len(sys.argv) > 1 and sys.argv[1] == "ask":
        if len(sys.argv) < 3:
            print("Usage: chat ask <question>")
            return
        handle_ask_cmd(" ".join(sys.argv[2:]))
    elif len(sys.argv) > 1 and sys.argv[1] == "tree":
        handle_tree_cmd()
    elif len(sys.argv) > 1 and sys.argv[1] == "symbols":
        if len(sys.argv) < 3:
            print("Usage: chat symbols <query>")
            return
        handle_symbols_cmd(" ".join(sys.argv[2:]))
    elif len(sys.argv) > 1 and sys.argv[1] == "plan":
        if len(sys.argv) < 3:
            print("Usage: chat plan <goal>")
            return
        handle_plan_cmd(" ".join(sys.argv[2:]))
    elif len(sys.argv) > 1 and sys.argv[1] == "implement":
        if len(sys.argv) < 3:
            print("Usage: chat implement <step_number>")
            return
        handle_implement_cmd(sys.argv[2])
    elif len(sys.argv) > 1 and sys.argv[1] == "impact":
        if len(sys.argv) < 3:
            print("Usage: chat impact <step_number>")
            return
        handle_impact_cmd(sys.argv[2])
    elif len(sys.argv) > 1 and sys.argv[1] == "safe-implement":
        if len(sys.argv) < 3:
            print("Usage: chat safe-implement <step_number>")
            return
        handle_safe_implement_cmd(sys.argv[2])
    elif len(sys.argv) > 1 and sys.argv[1] == "next":
        handle_next_cmd()
    elif len(sys.argv) > 1 and sys.argv[1] == "detach":
        handle_detach_cmd()
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