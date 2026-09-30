# Apply Progress: tui-installer

## Status: Part 1 Complete (Phases 1-2)

**Mode**: Standard (no Strict TDD)

## Completed Tasks

- [x] T1 — Add prompt_toolkit dependency to pyproject.toml
- [x] T2 — Create scripts/tui/ directory structure with __init__.py files
- [x] T3 — Create config_schemas.py with OPENCODE_SCHEMA, CLAUDE_SCHEMA, PI_SCHEMA, format_schema
- [x] T4 — Create install_logic.py with read_config, write_config, deep_merge, merge_entry, register_opencode, register_claude, register_pi
- [x] T5 — Create state.py with State dataclass, from_file, save, get_last_agent, set_preference
- [x] T6 — Create registry.py with _REGISTRY, register decorator, get_all, get_by_category, reset
- [x] T7 — Create app.py with TUIMenu class using prompt_toolkit

## Files Changed

| File | Action | What Was Done |
|------|--------|---------------|
| `pyproject.toml` | Modified | Added `tui = ["prompt_toolkit>=3.0"]` to optional-dependencies |
| `scripts/__init__.py` | Created | Package init for scripts module |
| `scripts/tui/__init__.py` | Created | TUI package init with module docstring |
| `scripts/tui/items/__init__.py` | Created | Items subpackage init |
| `scripts/tui/config_schemas.py` | Created | JSON templates + format_schema helper |
| `scripts/tui/install_logic.py` | Created | Atomic config I/O, deep merge, register functions |
| `scripts/tui/state.py` | Created | State dataclass with JSON persistence |
| `scripts/tui/registry.py` | Created | Decorator registry pattern for menu items |
| `scripts/tui/app.py` | Created | TUIMenu with prompt_toolkit Application |
| `openspec/changes/tui-installer/tasks.md` | Modified | Marked T1-T7 complete |

## Deviations from Design

1. **merge_entry signature**: Design uses `merge_entry(path, entry)` (file-level). Implementation uses `merge_entry(config, key, entry)` (pure dict function) per spec. Register functions handle file I/O. Added `deep_merge(base, override)` helper.
2. **PI schema values**: Design uses `"directTools": True, "lifecycle": "lazy"` matching install.ps1. Mission brief used different values. Used design values.
3. **State field name**: Design/mission uses `last_agent`, spec uses `last_run_agent`. Used `last_agent` per mission.
4. **TUIMenu class**: Design says "extends Application". Implementation uses composition (wraps Application) for cleaner async handling.
5. **Added format_schema()**: Helper in config_schemas.py for deep-copying and replacing `{python_exe}` placeholders, cleaner than manual string replacement.
6. **Added reset()**: In registry.py for test teardown.
7. **scripts/__init__.py**: Created to enable `python -m scripts.tui` execution.

## Issues Found

None — all modules import and function correctly.

## Remaining Tasks

- [ ] T8 — Create items/base.py (MenuItem ABC)
- [ ] T9 — Create items/opencode.py (OpenCode registration item)
- [ ] T10 — Create items/claude.py (Claude Desktop item)
- [ ] T11 — Create items/pi.py (Pi item)
- [ ] T12 — Create __main__.py (entry point)
- [ ] T13 — Create tests/tui/test_registry.py
- [ ] T14 — Create tests/tui/test_install_logic.py
- [ ] T15 — Create tests/tui/test_state.py
- [ ] T16 — Create tests/tui/test_items.py
- [ ] T17 — Manual TUI walkthrough
- [ ] T18 — Optional: install.ps1 subprocess

## Workload / PR Boundary

- Mode: single PR (Phases 1-2)
- Current work unit: PR 1 of 2 — Foundation + Core TUI
- Boundary: T1-T7 complete; T8-T18 belong to PR 2
- Estimated review budget impact: ~350 lines of new code

## Status

7/18 tasks complete. Ready for next batch (Phases 3-4) or sdd-verify for PR 1 scope.