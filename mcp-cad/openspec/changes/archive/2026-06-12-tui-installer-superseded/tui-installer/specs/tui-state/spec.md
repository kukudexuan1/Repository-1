# TUI State Persistence Specification

## Purpose

Defines the JSON-based state persistence layer that remembers user selections across TUI sessions, including last-run agent, custom paths, and preferences.

## Requirements

### Requirement: State File Location and Schema

The system MUST store state in `scripts/tui/state.json` with the following schema:

```json
{
  "last_run_agent": "opencode",
  "custom_paths": {},
  "preferences": {}
}
```

| Field | Type | Description |
|-------|------|-------------|
| `last_run_agent` | `str` | Name of the last successfully run agent item |
| `custom_paths` | `dict` | User-defined override paths (e.g., custom Pi settings path) |
| `preferences` | `dict` | Reserved for future UI preferences |

#### Scenario: State file created on first save

- GIVEN no `state.json` exists
- WHEN state is saved for the first time
- THEN the file MUST be created with the default schema
- AND `last_run_agent` MUST be `null` or empty string

#### Scenario: State file updated after item run

- GIVEN `state.json` exists with `last_run_agent: "opencode"`
- WHEN the user runs the Claude item successfully
- THEN `last_run_agent` MUST be updated to `"claude"`

### Requirement: Load State on Startup

The system MUST load `state.json` when the TUI starts. If the file is missing or contains malformed JSON, the system MUST use default values without crashing.

#### Scenario: Load valid state

- GIVEN `state.json` contains valid JSON matching the schema
- WHEN the TUI starts
- THEN state MUST be loaded and available to the app

#### Scenario: Missing state file

- GIVEN `state.json` does not exist
- WHEN the TUI starts
- THEN default state MUST be used
- AND no error MUST be displayed

#### Scenario: Malformed JSON in state file

- GIVEN `state.json` contains invalid JSON
- WHEN the TUI starts
- THEN default state MUST be used
- AND a warning message MAY be displayed

#### Scenario: Partial schema (missing fields)

- GIVEN `state.json` contains `{"last_run_agent": "pi"}` only
- WHEN the TUI starts
- THEN missing fields MUST be filled with defaults
- AND `last_run_agent` MUST be `"pi"`

### Requirement: Save State on Item Completion

The system MUST save state to `state.json` after each menu item completes successfully.

#### Scenario: Save after successful run

- GIVEN an agent item completes without error
- WHEN the item's `run()` returns
- THEN `state.py` MUST write the updated state to `state.json`

#### Scenario: No save on failure

- GIVEN an agent item fails with an exception
- WHEN the error is caught
- THEN state MUST NOT be updated
- AND `last_run_agent` MUST retain its previous value

### Requirement: Custom Paths Storage

The system MUST support storing custom file paths in `custom_paths`, keyed by agent name.

#### Scenario: Store custom Pi path

- GIVEN the user sets a custom Pi settings path
- WHEN state is saved
- THEN `custom_paths["pi"]` MUST contain the absolute path

#### Scenario: Retrieve custom path

- GIVEN `custom_paths["pi"]` was previously saved
- WHEN `PiItem.run()` queries state
- THEN it MUST receive the stored custom path
