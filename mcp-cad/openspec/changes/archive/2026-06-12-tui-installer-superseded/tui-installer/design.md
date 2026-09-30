# Design: tui-installer

## Technical Approach

A Python TUI module (`scripts/tui/`) provides interactive MCP agent registration for OpenCode, Claude Desktop, and Pi. The module integrates with the existing `install.ps1` for venv setup while handling all agent configuration in pure Python. Menu items are self-registering via a decorator — adding a new agent only requires creating a new file in `items/`.

## Architecture Decisions

| Decision | Chosen | Rationale |
|---|---|---|
| TUI framework | `prompt_toolkit` | Cross-platform, clean API, async-ready. Windows-compatible |
| Extensibility pattern | Decorator registry | New items self-register without touching core. No plugin loader complexity |
| Config format source | `config_schemas.py` centralized | Eliminates drift between install.ps1 templates and TUI |
| State persistence | JSON in repo (`scripts/tui/state.json`) | Matches install.ps1 location; repo tracking OK for project use |
| Config write safety | Atomic (temp + rename) | Avoids leaving corrupted JSON on crash |
| State write safety | Atomic (temp + rename) | Same as above |
| install.ps1 role | Non-interactive fallback | TUI is the primary flow; install.ps1 remains for scripted use |

## Data Flow

```
$ python -m scripts.tui
        |
   app.py loads
   registry.py → get_all() → all MenuItem subclasses
   state.py → from_file() → pre-selections from last run
        |
   prompt_toolkit event loop
        |
   User navigates and selects agents
        |
   items/opencode.py   → read/write opencode.json
   items/claude.py     → read/write %APPDATA%\Claude\claude_desktop_config.json
   items/pi.py         → read/write Pi settings.json
        |
   state.save() → state.json
```

## Module Structure

```
scripts/tui/
├── __init__.py
├── __main__.py          # Entry point: python -m scripts.tui
│   → loads app.app() and runs it
├── app.py               # prompt_toolkit Application
│   → KB: Enter=confirm, Esc=back/cancel, arrows=navigate
│   → render(): VBox with title + checkbox list + footer + errors
│   → on_item_run(): re-render menu with status message
├── registry.py           # @register decorator + global registry
│   → _REGISTRY dict keyed by category
│   → get_all() → list, get_by_category(cat) → filtered list
│   → @register(name, description, category) decorator
├── state.py              # State persistence
│   → State.from_file(path)
│   → .save() — atomic write
│   → .last_agent, .custom_paths, .preferences
├── config_schemas.py     # JSON templates
│   → OPENCODE_SCHEMA, CLAUDE_SCHEMA, PI_SCHEMA
├── install_logic.py       # Pure Python config I/O
│   → read_config(path), write_config(path, data)
│   → merge_entry(path, entry) — deep merge + atomic write
│   → register_opencode(), register_claude(), register_pi()
└── items/
    ├── __init__.py
    ├── base.py           # MenuItem ABC
    │   → abstract run(), name, description, category, is_enabled
    ├── opencode.py       # @register("opencode", ...) → opencode.json
    ├── claude.py         # @register("claude", ...) → claude_desktop_config.json
    └── pi.py             # @register("pi", ...) → Pi settings.json
```

## app.py — Application Design

```python
# scripts/tui/app.py
class TUIMenu(Application):
    def __init__(self, registry, state):
        self.registry = registry
        self.state = state
        self.selected = set()       # checkbox items
        self.error_msg = None
        self.status_msg = None

    def render(self):
        # VBox of:
        # - Label("mcp-cad Installer")
        # - [Checkbox] for each item in registry.get_all()
        # - Label("Status: ..." or "Error: ...")
        # - HP/ spanned footer: [Confirm]  [Cancel/Back]

    def keybinding_enter(self):
        # run selected items in order
        # for each: item.run() → ok → status="Done: {item.name}"
        #                       → err → error_msg = msg; stop
        # ask_to_save_and_exit()

    def keybinding_esc(self):
        # confirm quit if dirty, exit
```

## registry.py — Decorator Pattern

```python
# scripts/tui/registry.py
_REGISTRY: dict[str, list["MenuItem"]] = {}

def register(name: str, description: str, category: str = "agent"):
    def deco(cls):
        _REGISTRY.setdefault(category, []).append(cls())
        return cls
    return deco

def get_all() -> list["MenuItem"]:
    return [item for items in _REGISTRY.values() for item in items]

def get_by_category(cat: str) -> list["MenuItem"]:
    return _REGISTRY.get(cat, []).copy()
```

## items/base.py — MenuItem ABC

```python
# scripts/tui/items/base.py
from abc import ABC, abstractmethod

class MenuItem(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    def category(self) -> str: return "agent"

    @property
    def is_enabled(self) -> bool: return True

    @abstractmethod
    def run(self) -> None:  # raises on failure
        ...
```

## install_logic.py — Config I/O

```python
# scripts/tui/install_logic.py
import json, os
from pathlib import Path
from config_schemas import OPENCODE_SCHEMA, CLAUDE_SCHEMA, PI_SCHEMA

def read_config(path: str | Path) -> dict | None:
    p = Path(path)
    if not p.exists(): return None
    with p.open() as f: return json.load(f)

def write_config(path: str | Path, data: dict) -> None:
    p = Path(path)
    tmp = p.with_suffix('.tmp')
    with tmp.open('w') as f: json.dump(data, f, indent=2)
    tmp.replace(p)  # atomic on POSIX; works OK on Windows

def merge_entry(path: str | Path, entry_template: dict) -> bool:
    data = read_config(path) or {}
    # deep merge top-level keys only
    data.update(entry_template)
    write_config(path, data)
    return True

# Per-agent registration (raises on failure)
def register_opencode(project_dir: Path, venv_python: str) -> str: ...
def register_claude(venv_python: str) -> str: ...
def register_pi(venv_python: str, settings_path: str | None) -> str: ...
```

## state.py — State

```json
<!-- scripts/tui/state.json -->
{
  "last_agent": "opencode",
  "custom_paths": {
    "pi_settings": ""
  },
  "preferences": {}
}
```

## config_schemas.py — Templates

```python
# scripts/tui/config_schemas.py

OPENCODE_SCHEMA = {
    "$schema": "https://opencode.ai/config.json",
    "mcp": {
        "mcp-cad": {
            "type": "local",
            "command": ["{python_exe}", "-m", "mcp_cad"]
        }
    }
}

CLAUDE_SCHEMA = {
    "mcpServers": {
        "mcp-cad": {
            "command": "{python_exe}",
            "args": ["-m", "mcp_cad"]
        }
    }
}

PI_SCHEMA = {
    "mcpServers": {
        "mcp-cad": {
            "command": "{python_exe}",
            "args": ["-m", "mcp_cad"],
            "directTools": True,
            "lifecycle": "lazy"
        }
    }
}
```

## Dependencies

```toml
# pyproject.toml
[project.optional-dependencies]
tui = ["prompt_toolkit>=3.0"]
```

## Tests Strategy

| Test file | What it covers | Key technique |
|---|---|---|
| `tests/tui/test_registry.py` | @register decorator, get_all/by_category | simple class inspection, no I/O |
| `tests/tui/test_install_logic.py` | read/write/merge with temp files | `tmp_path` pytest fixture |
| `tests/tui/test_state.py` | from_file/save cycle with tmp_path | `tmp_path` fixture |
| `tests/tui/test_items.py` | each MenuItem subclass, mock install_logic | `unittest.mock.patch` |

## Open Questions

1. **state.json location** — currently scripts/tui/state.json; could also be `$HOME/.config/mcp-cad/` or `%APPDATA%`. Repo location fine for now.
2. **Uninstall/cleanup** — not in scope for this change. Left as future work.
3. **Install.ps1 subprocess** — T15 only. If install.ps1 changes its JSON templates, TUI would drift. Mitigated by config_schemas.py as single source of truth.
