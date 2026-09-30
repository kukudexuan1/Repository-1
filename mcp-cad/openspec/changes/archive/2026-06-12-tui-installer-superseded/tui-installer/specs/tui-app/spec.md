# TUI Application Specification

## Purpose

Defines the interactive terminal application that serves as the entry point for agent registration. Users launch it via `python -m scripts.tui` and navigate menus to select, configure, and register MCP agents.

## Requirements

### Requirement: Entry Point and Launch

The system MUST provide a `scripts/tui/__main__.py` that launches the TUI when invoked as `python -m scripts.tui`. If `prompt_toolkit` is not installed, the system MUST print a clear error message with installation instructions and exit with code 1.

#### Scenario: Successful launch with prompt_toolkit

- GIVEN `prompt_toolkit>=3` is installed
- WHEN the user runs `python -m scripts.tui`
- THEN the TUI application MUST start and display the main menu

#### Scenario: Missing prompt_toolkit

- GIVEN `prompt_toolkit` is NOT installed
- WHEN the user runs `python -m scripts.tui`
- THEN the system MUST print: "prompt_toolkit is required. Install with: pip install prompt_toolkit>=3"
- AND exit with code 1

### Requirement: Main Menu Rendering

The system MUST render a main menu on startup showing a welcome banner followed by a list of registered `MenuItem` entries. Each entry displays its `title`, `description`, and `is_enabled` status.

#### Scenario: Welcome banner display

- GIVEN the TUI starts successfully
- WHEN the main menu renders
- THEN it MUST display a welcome banner with the application name "mcp-cad TUI Installer"
- AND the banner MUST be visually separated from the menu items

#### Scenario: Menu items display

- GIVEN registered menu items exist in the registry
- WHEN the main menu renders
- THEN each item MUST show: title (bold), description (dimmed), and enabled/disabled indicator
- AND items MUST be navigable with arrow keys

### Requirement: Keybindings

The system MUST support the following global keybindings:

| Key | Action |
|-----|--------|
| `Enter` | Confirm selection / run selected item |
| `Esc` | Go back to previous screen / cancel current operation |
| `Up` / `Down` | Navigate menu items |
| `q` | Quit the application |

#### Scenario: Navigate with arrow keys

- GIVEN the main menu is displayed with 3+ items
- WHEN the user presses `Down`
- THEN the selection highlight MUST move to the next item
- AND wrapping from last to first item MUST occur

#### Scenario: Confirm selection

- GIVEN an item is highlighted
- WHEN the user presses `Enter`
- THEN the item's `run()` method MUST be called
- AND a result screen MUST display success or error

#### Scenario: Cancel and go back

- GIVEN the user is on a result screen after running an item
- WHEN the user presses `Esc`
- THEN the system MUST return to the main menu

#### Scenario: Quit application

- GIVEN the user is on any screen
- WHEN the user presses `q`
- THEN the application MUST exit cleanly with code 0

### Requirement: Error Display

The system MUST display error messages inline below the menu when an operation fails. The error message MUST clear on the next keypress.

#### Scenario: Error shown after failed operation

- GIVEN a menu item's `run()` raises an exception
- WHEN the error is caught
- THEN a red error message MUST display below the menu
- AND the message MUST include the exception text

#### Scenario: Error clears on keypress

- GIVEN an error message is displayed
- WHEN the user presses any navigation key
- THEN the error message MUST be cleared

### Requirement: State Persistence Integration

The system MUST load saved state on startup via `state.py` and pre-select items based on `last_run_agent`. State MUST be saved after each item completes successfully.

#### Scenario: Load state on startup

- GIVEN `state.json` exists with `last_run_agent: "opencode"`
- WHEN the TUI starts
- THEN the OpenCode item MUST be pre-selected (highlighted)

#### Scenario: No state file on first run

- GIVEN `state.json` does not exist
- WHEN the TUI starts
- THEN the first item in the list MUST be selected by default
- AND no error MUST be shown
