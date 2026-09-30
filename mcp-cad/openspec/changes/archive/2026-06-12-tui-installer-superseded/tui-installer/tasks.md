# Tasks: tui-installer

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~410–510 |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes — 2 PRs |
| Chain strategy | feature-branch-chain |
| Suggested split | PR 1 (Phases 1–2) → PR 2 (Phases 3–5) |
| Delivery strategy | ask-on-risk |

---

## Phase 1: Foundation

No dependencies — start here.

### T1 — Add prompt_toolkit dependency ✅

**What**: Add `prompt_toolkit>=3.0` as optional dependency.

**How**: Add to `pyproject.toml` under `[project.optional-dependencies]` as `tui = ["prompt_toolkit>=3.0"]`.

**Verification**: `pip install -e ".[tui]"` succeeds and `python -c "import prompt_toolkit"` works.

---

### T2 — Create directory structure ✅

**What**: Create `scripts/tui/` with `__init__.py` and `items/__init__.py`.

**How**:
```
scripts/__init__.py
scripts/tui/__init__.py
scripts/tui/items/__init__.py
```

**Verification**: `python -c "from scripts.tui import TUIMenu; from scripts.tui.items import opencode, claude, pi"` (may fail import if not all files exist — structural check only for now).

---

### T3 — Create config_schemas.py ✅

**What**: JSON templates for all three agent configuration formats.

**How**: Create `scripts/tui/config_schemas.py` with:
- `OPENCODE_SCHEMA` — type/local/command array
- `CLAUDE_SCHEMA` — mcpServers dict
- `PI_SCHEMA` — mcpServers with directTools/lifecycle
- All use `{python_exe}` placeholder

**Verification**: `python -c "from scripts.tui.config_schemas import OPENCODE_SCHEMA, CLAUDE_SCHEMA, PI_SCHEMA; assert 'python_exe' in str(OPENCODE_SCHEMA)"`

---

### T4 — Create install_logic.py ✅

**What**: Pure Python config read/write/merge for all agents.

**How**: Create `scripts/tui/install_logic.py`:
- `read_config(path)` — returns dict or None
- `write_config(path, data)` — atomic via temp+rename
- `merge_entry(config, key, entry)` — deep merge entry into config dict under key
- `deep_merge(base, override)` — recursive dict merge
- `register_opencode(project_dir, venv_python)` — read opencode.json, merge mcp-cad entry
- `register_claude(venv_python)` — read %APPDATA%\Claude\claude_desktop_config.json, create if missing, merge
- `register_pi(venv_python, settings_path)` — same pattern for Pi

**Verification**: See Phase 4 tests.

---

## Phase 2: Core TUI

Depends on T3.

### T5 — Create state.py ✅

**What**: JSON state persistence with from_file/save cycle.

**How**: Create `scripts/tui/state.py`:
- `State` dataclass: `last_agent`, `custom_paths: dict`, `preferences: dict`
- `State.from_file(path)` classmethod — loads from JSON, handles missing/malformed
- `.save(path)` — atomic write

**Verification**: `tmp_path` fixture tests in Phase 4.

---

### T6 — Create registry.py ✅

**What**: @register decorator + global registry.

**How**: Create `scripts/tui/registry.py`:
- `_REGISTRY` dict keyed by category
- `get_all()` → list of all items; `get_by_category(cat)` → filtered list
- `register(name, description, category)` decorator function
- On import of `items/` submodules, decorated classes self-register

**Verification**: `pytest tests/tui/test_registry.py`

---

### T7 — Create app.py ✅

**What**: prompt_toolkit Application with keybindings.

**How**: Create `scripts/tui/app.py`:
```python
# Imports prompt_toolkit
# TUIMenu uses Application internally (composition)
# __init__(state, state_path)
# Dynamic layout with FormattedTextControl callables
# KeyBindings:
#   Enter → run selected items, show status/errors
#   Space → toggle checkbox
#   Esc/q → save state if dirty and exit
#   Arrow up/down → navigate (wrapping)
# Pre-select from state.last_agent if saved
```

**Note**: Keep simple — checkbox list + footer only. Status/error messages show below the menu.

**Verification**: Manual: `python -m scripts.tui` runs and shows menu.

---

## Phase 3: Menu Items

Depends on T6 (registry base class). Items T8–T11 are independently testable and can be built in parallel.

### T8 — Create items/base.py ✅

**What**: MenuItem ABC.

**How**: Create `scripts/tui/items/base.py`:
- `MenuItem` ABC with abstract methods:
  - `name: str` property (abstract)
  - `description: str` property (abstract)
  - `category: str` property → default "agent"
  - `is_enabled: bool` property → default True
  - `run(self, venv_python: str)` abstract method → raises on failure

**Verification**: `python -c "from scripts.tui.items.base import MenuItem"`

---

### T9 — Create items/opencode.py ✅

**What**: OpenCode registration item.

**How**: Create `scripts/tui/items/opencode.py`:
- Import `registry.register` decorator
- Import `install_logic.register_opencode`
- Class `_OpenCodeItem(MenuItem)` with name="opencode", description
- `run()`: detect project_dir from state or cwd, detect venv python from state or search
- Decorator: `@register("opencode", "Register mcp-cad in opencode.json", category="agent")`

**Verification**: Testable with mock install_logic.

---

### T10 — Create items/claude.py ✅

**What**: Claude Desktop registration item.

**How**: Create `scripts/tui/items/claude.py`:
- Same pattern as opencode.py
- `@register("claude", "Register mcp-cad in Claude Desktop config", category="agent")`
- uses `register_claude(install_logic)`

**Verification**: Testable with mock install_logic.

---

### T11 — Create items/pi.py ✅

**What**: Pi registration item.

**How**: Create `scripts/tui/items/pi.py`:
- Same pattern
- `@register("pi", "Register mcp-cad in Pi settings.json", category="agent")`
- uses `register_pi(install_logic)`

**Verification**: Testable with mock install_logic.

---

## Phase 4: Entry Point + Tests

Depends on T7 (app), T8–T11 (items). All test files below can be written in parallel once foundations exist.

### T12 — Create __main__.py ✅

**What**: Entry point for `python -m scripts.tui`.

**How**: Create `scripts/tui/__main__.py`:
```python
from scripts.tui.app import TUIMenu
from scripts.tui.registry import get_all
from scripts.tui.state import State

def main():
    project_dir = Path.cwd()
    items = get_all()
    state = State.from_file(project_dir / "scripts" / "tui" / "state.json")
    menu = TUIMenu(items, state)
    menu.run()

if __name__ == "__main__":
    main()
```

**Verification**: `python -m scripts.tui` starts the TUI.

---

### T13 — Create tests/tui/test_registry.py ✅

**What**: Test registry and decorator pattern.

**How**: `tests/tui/test_registry.py`:
- test `@register` adds class to registry
- test `get_all()` returns registered items
- test `get_by_category("agent")` filters correctly
- test no-op if item already registered

**Verification**: `pytest tests/tui/test_registry.py -v`

---

### T14 — Create tests/tui/test_install_logic.py ✅

**What**: Test config I/O with tmp_path fixture.

**How**: `tests/tui/test_install_logic.py`:
- `test_read_config_missing` → returns None
- `test_write_config_atomic` → file exists after write
- `test_merge_entry` → existing keys preserved, new keys added
- `test_merge_entry_creates_file` → creates if missing
- `test_register_opencode` → merges mcp-cad entry into opencode.json

Use `tmp_path` pytest fixture for all file operations.

**Verification**: `pytest tests/tui/test_install_logic.py -v`

---

### T15 — Create tests/tui/test_state.py ✅

**What**: Test state from_file/save cycle.

**How**: `tests/tui/test_state.py`:
- `test_from_file_loads_existing` → reads valid state.json
- `test_from_file_missing` → returns default State
- `test_from_file_malformed` → returns default State
- `test_save_atomic` → atomic write confirmed

**Verification**: `pytest tests/tui/test_state.py -v`

---

### T16 — Create tests/tui/test_items.py ✅

**What**: Test each MenuItem subclass in isolation.

**How**: `tests/tui/test_items.py`:
- Patch install_logic functions with mock
- test opencode item: `run()` calls register_opencode with correct path
- test claude item: `run()` calls register_claude
- test pi item: `run()` calls register_pi with custom path support
- test disabled item: `is_enabled = False` skipped

**Verification**: `pytest tests/tui/test_items.py -v`

---

## Phase 5: Integration

### T17 — Manual TUI walkthrough

**What**: Run full TUI, verify every step works end-to-end.

**How**: 
1. `python -m scripts.tui` — menu renders
2. Navigate to an agent, press Enter — registration succeeds
3. Check config file was updated correctly
4. Run again — pre-selections from state.json
5. Esc from menu — confirm quit

**Verification**: Manual only.

---

### T18 — Optional: subprocess to install.ps1

**What**: From TUI, optionally run venv setup via install.ps1.

**How**: Add a "system" category item that runs `install.ps1` via `subprocess.run` if venv doesn't exist yet. Only shown if relevant.

**Note**: This is optional — depends on user need.

**Verification**: Manual only.

---

## Open Questions

1. **state.json location** — currently `scripts/tui/state.json` (repo-local). Acceptable for now.
2. **Uninstall/cleanup** — not in scope, future work.
3. **Install.ps1 template drift** — mitigated by config_schemas.py as single source of truth.
