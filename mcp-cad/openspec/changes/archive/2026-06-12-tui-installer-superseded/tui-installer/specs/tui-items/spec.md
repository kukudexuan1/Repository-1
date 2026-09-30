# Agent Registration Items Specification

## Purpose

Defines the concrete `MenuItem` implementations for registering mcp-cad with OpenCode, Claude, and Pi agents. Each item reads the agent's config file, merges the mcp-cad server entry, and writes back — never deleting existing entries.

## Requirements

### Requirement: OpenCode Agent Registration

The system MUST implement an `OpenCodeItem` that reads the project's `opencode.json`, merges an mcp-cad server entry with a command pointing to the project venv Python, and writes the updated config.

#### Scenario: Merge mcp-cad into existing opencode.json

- GIVEN `opencode.json` exists with other MCP servers configured
- WHEN `OpenCodeItem.run()` executes
- THEN it MUST add/update the mcp-cad entry with `"command"` pointing to the venv `python.exe`
- AND all other entries MUST remain unchanged

#### Scenario: Handle missing opencode.json

- GIVEN `opencode.json` does not exist
- WHEN `OpenCodeItem.run()` executes
- THEN it MUST offer to create the file with the mcp-cad schema
- AND if the user confirms, a valid `opencode.json` MUST be created

#### Scenario: Handle malformed JSON

- GIVEN `opencode.json` contains invalid JSON
- WHEN `OpenCodeItem.run()` executes
- THEN it MUST display the parse error
- AND offer to fix or skip the operation

#### Scenario: Handle permission denied

- GIVEN the user lacks write permission to `opencode.json`
- WHEN `OpenCodeItem.run()` executes
- THEN it MUST display a permission error
- AND MUST NOT corrupt the existing file

### Requirement: Claude Agent Registration

The system MUST implement a `ClaudeItem` that reads `%APPDATA%\Claude\claude_desktop_config.json`, merges the mcp-cad server entry, and creates the file with the correct schema if it does not exist.

#### Scenario: Merge into existing Claude config

- GIVEN `claude_desktop_config.json` exists with other servers
- WHEN `ClaudeItem.run()` executes
- THEN it MUST add/update the mcp-cad server entry
- AND all other server entries MUST remain unchanged

#### Scenario: Create missing Claude config

- GIVEN `%APPDATA%\Claude\` directory exists but no config file
- WHEN `ClaudeItem.run()` executes
- THEN it MUST create `claude_desktop_config.json` with the mcp-cad schema

#### Scenario: Missing Claude directory

- GIVEN `%APPDATA%\Claude\` directory does not exist
- WHEN `ClaudeItem.run()` executes
- THEN it MUST offer to create the directory and config file

### Requirement: Pi Agent Registration

The system MUST implement a `PiItem` that reads the Pi `settings.json` (path configurable via state), merges the mcp-cad server entry, and writes back.

#### Scenario: Merge into existing Pi settings

- GIVEN Pi `settings.json` exists
- WHEN `PiItem.run()` executes
- THEN it MUST add/update the mcp-cad server entry
- AND all other settings MUST remain unchanged

#### Scenario: Configurable Pi path

- GIVEN the user has set a custom Pi settings path in state
- WHEN `PiItem.run()` executes
- THEN it MUST use the custom path instead of the default

### Requirement: Add-Only Merge Strategy

All three agent items MUST follow an add-only merge strategy: they add or update the mcp-cad entry only, never deleting or modifying other entries in the config file.

#### Scenario: Other entries preserved after merge

- GIVEN a config file with 3 existing server entries
- WHEN any agent item runs and merges mcp-cad
- THEN the file MUST contain 4 entries (3 original + mcp-cad)
- AND the original 3 entries MUST be byte-identical to before

### Requirement: Success Feedback

After successful registration, the system MUST display a success message showing the path to the modified config file.

#### Scenario: Success message displays path

- GIVEN an agent item completes registration successfully
- WHEN the result screen renders
- THEN it MUST display: "Successfully registered mcp-cad in: <absolute_path>"

### Requirement: Rollback on Failure

If any step fails after the config file has been modified, the system MUST restore the original file from a backup.

#### Scenario: Rollback restores original

- GIVEN a backup was created before modification
- WHEN a write error occurs after partial modification
- THEN the original file MUST be restored from backup
- AND the error MUST be displayed to the user
