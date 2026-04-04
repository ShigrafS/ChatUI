"""Handles model selection, listing, and config persistence."""

import json
import os
from pathlib import Path

# bundled models list lives next to this file
_MODELS_FILE = Path(__file__).parent / "models.json"

# user config lives at ~/.nimui/config.json
_CONFIG_DIR = Path.home() / ".nimui"
_CONFIG_FILE = _CONFIG_DIR / "config.json"


def _load_models_registry():
    """Load the bundled models.json."""
    with open(_MODELS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_config():
    """Read user config, return empty dict if missing."""
    if _CONFIG_FILE.exists():
        with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_config(cfg):
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def get_current_model():
    """Return the active model — config override or default."""
    cfg = _load_config()
    if "current_model" in cfg:
        return cfg["current_model"]
    # fall back to default from registry
    registry = _load_models_registry()
    return registry["default"]


def set_model(model_name):
    """Switch to a different model. Validates against the registry."""
    registry = _load_models_registry()
    available = registry["models"]

    if model_name not in available:
        # try partial match (e.g. "mistral" matches "mistralai/mistral-7b-instruct")
        matches = [m for m in available if model_name.lower() in m.lower()]
        if len(matches) == 1:
            model_name = matches[0]
        elif len(matches) > 1:
            print(f"Ambiguous model name '{model_name}'. Did you mean one of:")
            for m in matches:
                print(f"  - {m}")
            return
        else:
            print(f"Model '{model_name}' not found in registry.")
            print("Use `chat model --list` to see available models.")
            return

    cfg = _load_config()
    cfg["current_model"] = model_name
    _save_config(cfg)
    print(f"Switched to: {model_name}")


def list_models():
    """Print all available models, marking the active one."""
    registry = _load_models_registry()
    current = get_current_model()

    print("Available models:\n")
    for m in registry["models"]:
        marker = " ← active" if m == current else ""
        print(f"  • {m}{marker}")
    print()
