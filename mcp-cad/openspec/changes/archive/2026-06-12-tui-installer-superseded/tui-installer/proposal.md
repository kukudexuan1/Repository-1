# Proposal: TUI Installer

## Intent

Replace manual agent registration with an interactive Python TUI that lets users select, configure, and register any combination of OpenCode, Claude, and Pi agents. Today, registration is script-driven and requires users to edit JSON or run PowerShell manually. A TUI reduces errors, guides non-technical users, and makes adding new agents a matter of dropping in a new module—no core changes required.

## Scope

### In Scope
- Python TUI under `scripts/tui/` using `prompt_toolkit`
- Decorator-based registry pattern for pluggable menu items
- Pure-Python config registration (JSON update, no install.ps1 changes)
- Optional invocation of `install.ps1` for venv/materialized setup
- Config schemas in `config_schemas.py` to avoid format drift
- Per-agent items: `opencode.py`, `claude.py`, `pi.py`
- Tests: registry, items, install logic, state

### Out of Scope
- Rewriting `install.ps1` core logic or venv creation from scratch
- GUI version (web or desktop)
- New CAD backends or MCP tools
- Automated CI/CD installer distribution

## Capabilities

### New Capabilities
- `tui-agent-installer`: Interactive menu to select and register OpenCode, Claude, and Pi agents
- `tui-pluggable-registry`: Decorator-based self-registration so new agents add a file without touching core code

### Modified Capabilities
- None (this is an additive installer tool)

## Approach

Approach 2: Pure-Python registration.

Build a `prompt_toolkit`-based TUI in `scripts/tui/` with the following modules:

| Module | Responsibility |
|---|---|
| `app.py` | Main loop, key bindings, screen layout |
| `registry.py` | `@register_item` decorator + `MenuItem` collection |
| `state.py` | Session selections, validation flags |
| `install_logic.py` | JSON read/write, backup, rollback per agent |
| `config_schemas.py` | Pydantic/dataclass schemas for each agent config |
| `items/base.py` | `MenuItem` protocol / ABC |
| `items/opencode.py` | OpenCode registration logic |
| `items/claude.py` | Claude registration logic |
| `items/pi.py` | Pi registration logic |

The TUI optionally shells out to `install.ps1` for venv/materialized setup if the user chooses, but never replaces it. `prompt_toolkit` is declared as an optional dependency under `installer = ["prompt_toolkit>=3"]`.

### Alternatives Considered

| Approach | Why Rejected |
|---|---|
| **1: Subprocess wrap** | Kept install.ps1 as the single source of truth but forced users to still edit JSON manually; added process overhead without solving interactivity |
| **3: Extract shared logic** | Required refactoring install.ps1 into a library, which is harder to maintain and test than a clean Python sidecar |

## Directory Structure

```
scripts/
└── tui/
    ├── __main__.py
    ├── app.py
    ├── registry.py
    ├── state.py
    ├── install_logic.py
    ├── config_schemas.py
    └── items/
        ├── base.py
        ├── opencode.py
        ├── claude.py
        └── pi.py
tests/
└── tui/
    ├── test_registry.py
    ├── test_items.py
    ├── test_install_logic.py
    └── test_state.py
```

## API Surface

| Consumer | Before | After |
|---|---|---|
| End user | Edit JSON / run install.ps1 manually | Run `python -m scripts.tui` and follow menus |
| Agent developer | Edit install.ps1 or core scripts | Add `items/<agent>.py` with `@register_item` |
| CI / automation | N/A | Can still call `install.ps1` directly; TUI is optional |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Config format drift between install.ps1 and TUI | Med | Centralize schemas in `config_schemas.py`; add unit tests that validate both read/write paths |
| `prompt_toolkit` as new dependency | Low | Optional dependency under `[project.optional-dependencies]`; TUI fails gracefully with a message if missing |
| `feature/tui-installer` equals main | Low | Branch is currently up to date; rebase before merge if main moves |
| Cross-platform terminal quirks (Windows) | Med | Test on Windows Terminal, PowerShell, and CMD; avoid advanced `prompt_toolkit` widgets that break on legacy consoles |

## Rollback Plan

1. Revert `pyproject.toml` optional dependency addition.
2. Delete `scripts/tui/` and `tests/tui/`.
3. `install.ps1` is untouched, so existing manual registration remains fully functional.

## Dependencies

- `prompt_toolkit>=3` (optional)
- `pytest` for test verification
- Existing `install.ps1` for optional venv/materialized setup

## Success Criteria

- [ ] `python -m scripts.tui` launches and displays all 3 agents
- [ ] Selecting an agent and confirming writes valid JSON config
- [ ] Adding a new agent requires only a new file in `items/` + `@register_item`
- [ ] All 4 test modules pass (`test_registry`, `test_items`, `test_install_logic`, `test_state`)
- [ ] `install.ps1` remains unmodified and still works standalone
- [ ] TUI exits gracefully when `prompt_toolkit` is not installed
