# Pure Python Registration Logic Specification

## Purpose

Defines the decoupled, testable Python functions that handle JSON config read/write and merging for agent registration. This logic is fully independent from PowerShell `install.ps1` and requires no COM or Inventor dependencies.

## Requirements

### Requirement: Config Schemas

The system MUST define JSON config templates in `scripts/tui/config_schemas.py` for all three agents, ensuring format consistency between TUI and `install.ps1`.

#### Scenario: OpenCode schema exists

- GIVEN `config_schemas.py` is imported
- THEN it MUST export an OpenCode config template with the mcp-cad server structure
- AND the template MUST include `"command"` pointing to a venv Python placeholder

#### Scenario: Claude schema exists

- GIVEN `config_schemas.py` is imported
- THEN it MUST export a Claude desktop config template with the mcp-cad server entry
- AND the template MUST follow the Claude MCP server schema

#### Scenario: Pi schema exists

- GIVEN `config_schemas.py` is imported
- THEN it MUST export a Pi settings template with the mcp-cad server entry

### Requirement: read_config Function

The system MUST provide `read_config(path: str) -> dict` in `scripts/tui/install_logic.py` that reads and parses a JSON config file.

#### Scenario: Read valid JSON config

- GIVEN a file at `path` contains valid JSON
- WHEN `read_config(path)` is called
- THEN it MUST return a parsed `dict`

#### Scenario: File not found

- GIVEN no file exists at `path`
- WHEN `read_config(path)` is called
- THEN it MUST raise `FileNotFoundError`

#### Scenario: Malformed JSON

- GIVEN a file at `path` contains invalid JSON
- WHEN `read_config(path)` is called
- THEN it MUST raise `json.JSONDecodeError`

### Requirement: write_config Function

The system MUST provide `write_config(path: str, data: dict) -> None` in `scripts/tui/install_logic.py` that writes a dict as formatted JSON.

#### Scenario: Write valid config

- GIVEN a dict with valid config data
- WHEN `write_config(path, data)` is called
- THEN the file MUST contain valid, indented JSON
- AND the file MUST be readable by `read_config(path)`

#### Scenario: Write creates parent directories

- GIVEN the parent directory of `path` does not exist
- WHEN `write_config(path, data)` is called
- THEN it MUST create the parent directories before writing

### Requirement: merge_entry Function

The system MUST provide `merge_entry(config: dict, key: str, entry: dict) -> dict` that adds or updates a single entry within a config dict, preserving all other keys.

#### Scenario: Add new entry

- GIVEN a config dict with no `"mcp-cad"` key
- WHEN `merge_entry(config, "mcp-cad", {...})` is called
- THEN the returned dict MUST contain the new entry
- AND all existing keys MUST be unchanged

#### Scenario: Update existing entry

- GIVEN a config dict with an existing `"mcp-cad"` key (old values)
- WHEN `merge_entry(config, "mcp-cad", {...})` is called
- THEN the `"mcp-cad"` entry MUST be replaced with the new values
- AND all other keys MUST be unchanged

#### Scenario: Deep merge for nested configs

- GIVEN a config with nested structures under `"mcp-cad"`
- WHEN `merge_entry` is called
- THEN nested keys in the new entry MUST be merged, not replaced wholesale

### Requirement: register_all Function

The system MUST provide `register_all(agent: str, config_path: str, entry: dict) -> str` that orchestrates read-merge-write for a single agent, returning the path of the modified file.

#### Scenario: Full registration flow

- GIVEN a valid config file and entry dict
- WHEN `register_all("opencode", path, entry)` is called
- THEN it MUST read the config, merge the entry, write back, and return the path

#### Scenario: Rollback on write failure

- GIVEN `register_all` is called
- WHEN the write step fails after the config has been modified
- THEN the original file MUST be restored from backup
- AND the exception MUST be re-raised

### Requirement: Unit Testability

All functions in `install_logic.py` MUST be testable without COM, Inventor, or any external process. They operate purely on dicts and file paths.

#### Scenario: Test without Inventor

- GIVEN a unit test imports `install_logic`
- WHEN the test calls `merge_entry`, `read_config`, `write_config`
- THEN no COM initialization MUST occur
- AND no Inventor process MUST be launched

#### Scenario: Test with temp files

- GIVEN a unit test uses `tempfile` for config paths
- WHEN the test calls `register_all`
- THEN it MUST operate on the temp file
- AND the temp file MUST be cleaned up after the test
