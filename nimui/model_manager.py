"""Handles model selection, listing, searching, and config persistence."""

import json
import os
from pathlib import Path

# bundled models list lives next to this file
_MODELS_FILE = Path(__file__).parent / "models.json"

# user config at ~/.nimui/config.json
_CONFIG_DIR = Path.home() / ".nimui"
_CONFIG_FILE = _CONFIG_DIR / "config.json"


def _load_registry():
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


def _all_models(registry):
    """Flatten all models across all categories."""
    models = []
    for cat in registry["categories"].values():
        models.extend(cat["models"])
    return models


def get_current_model():
    """Return the active model — config override or default."""
    cfg = _load_config()
    if "current_model" in cfg:
        return cfg["current_model"]
    return _load_registry()["default"]


def set_model(model_name):
    """Switch to a different model. Validates against registry."""
    registry = _load_registry()
    available = _all_models(registry)

    if model_name not in available:
        # try partial match
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
            print("Use `chat model --search <term>` to find models.")
            return

    cfg = _load_config()
    cfg["current_model"] = model_name
    _save_config(cfg)
    print(f"Switched to: {model_name}")


def list_models(group=None):
    """List models by category or show categories overview."""
    registry = _load_registry()
    current = get_current_model()
    categories = registry["categories"]

    if group is None:
        # show category summary
        print("\nAvailable model groups:\n")
        for key, cat in categories.items():
            count = len(cat["models"])
            # hacky way to pad the key, but it works
            print(f"  {key:<20} {cat['description']} ({count} models)")
        print(f"\nUse: chat model --list <group>")
        print(f"     chat model --list all")
        print(f"     chat model --search <term>\n")
        return

    if group == "all":
        # dump everything, with warning
        print("\n⚠  Showing all models (this is a long list)\n")
        for key, cat in categories.items():
            _print_category(key, cat, current)
        return

    # specific category
    if group not in categories:
        print(f"Unknown group '{group}'. Available groups:")
        for key in categories:
            print(f"  - {key}")
        return

    cat = categories[group]
    _print_category(group, cat, current)


def _print_category(key, cat, current):
    """Print a single category's models."""
    print(f"\n  {cat['name']}  ({key})")
    print(f"  {cat['description']}\n")
    for m in cat["models"]:
        marker = " ← active" if m == current else ""
        print(f"    • {m}{marker}")
    print()


def search_models(term):
    """Search across all models."""
    registry = _load_registry()
    current = get_current_model()
    all_m = _all_models(registry)

    matches = [m for m in all_m if term.lower() in m.lower()]

    if not matches:
        print(f"No models matching '{term}'.")
        return

    print(f"\nMatching models ({len(matches)} results):\n")
    for m in matches:
        marker = " ← active" if m == current else ""
        print(f"  • {m}{marker}")
    print()
