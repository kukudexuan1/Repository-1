# MCP Tool Registration — Delta Spec

## ADDED Requirements

### Requirement: Generic Tool Modules

The system SHALL organize MCP tool implementations into domain-specific modules under `mcp_cad/tools/`:

| Module | Tools |
|--------|-------|
| `connection.py` | `inventor_connect`, `inventor_health`, `inventor_disconnect` |
| `documents.py` | `doc_open`, `doc_new_part`, `doc_new_assembly`, `doc_save`, `doc_save_as`, `doc_close` |
| `sketches.py` | `sketch_create`, `sketch_line`, `sketch_circle`, `sketch_arc`, `sketch_rectangle`, `sketch_dimension` |
| `features.py` | `extrude`, `revolve`, `fillet`, `chamfer` |
| `parameters.py` | `param_list`, `param_get`, `param_set`, `param_set_expression` |
| `properties.py` | `iproperty_get`, `iproperty_set`, `iproperty_summary`, `iproperty_custom_get`, `iproperty_custom_set` |
| `export.py` | `export_step`, `export_stl`, `export_pdf`, `export_dxf` |

#### Scenario: Each tool module accepts a provider

- GIVEN a tool module like `mcp_cad/tools/features.py`
- WHEN a tool function is defined
- THEN it MUST accept `provider: CADProvider` as its first parameter (or via closure)
- AND it MUST delegate to `provider.feature_ops.extrude(...)` etc.

#### Scenario: Tool modules have zero Inventor imports

- GIVEN any file in `mcp_cad/tools/`
- WHEN inspected for imports
- THEN it MUST NOT import from `mcp_cad.inventor.*` or `mcp_cad.providers.*`
- AND it MUST import ONLY from `mcp_cad.core.protocol`, `mcp_cad.errors`, and `mcp_cad.tools`

### Requirement: Generic register_tools Function

The system SHALL provide a `register_tools(mcp_instance: FastMCP, provider: CADProvider)` function in `mcp_cad/tools/__init__.py` that registers all 32 MCP tools on the FastMCP instance.

#### Scenario: register_tools accepts protocol only

- GIVEN the `register_tools` function
- WHEN called with `mcp_instance` and a `CADProvider`
- THEN it MUST register all 32 tools with identical names and signatures as before
- AND it MUST NOT accept individual manager instances (driver, doc_mgr, sketch_mgr, etc.)

#### Scenario: All 32 tools preserved

- GIVEN the new `register_tools` function
- WHEN tools are registered
- THEN the following 32 tools MUST exist with identical signatures:
  `inventor_connect`, `inventor_health`, `inventor_disconnect`,
  `doc_open`, `doc_new_part`, `doc_new_assembly`, `doc_save`, `doc_save_as`, `doc_close`,
  `sketch_create`, `sketch_line`, `sketch_circle`, `sketch_arc`, `sketch_rectangle`, `sketch_dimension`,
  `extrude`, `revolve`, `fillet`, `chamfer`,
  `param_list`, `param_get`, `param_set`, `param_set_expression`,
  `iproperty_get`, `iproperty_set`, `iproperty_summary`, `iproperty_custom_get`, `iproperty_custom_set`,
  `export_step`, `export_stl`, `export_pdf`, `export_dxf`

### Requirement: Error Envelope Pattern Preserved

Each tool function MUST catch `InventorDisconnectedError` and `InventorCOMError` and convert them to the standard `{success: False, error: str}` envelope, matching the current behavior exactly.

#### Scenario: Disconnected error returns standard envelope

- GIVEN any registered tool
- WHEN the provider raises `InventorDisconnectedError`
- THEN the tool MUST return `{"success": False, "error": "<message>"}`
- AND it MUST NOT propagate the exception

#### Scenario: COM error returns standard envelope

- GIVEN any registered tool
- WHEN the provider raises `InventorCOMError`
- THEN the tool MUST return `{"success": False, "error": "<message>"}`

### Requirement: server.py Depends on Protocol Only

The `mcp_cad/server.py` module MUST import ONLY from `mcp_cad.core.protocol` and the adapter factory. It MUST have zero imports from `mcp_cad.inventor.*` or `mcp_cad.providers.*`.

#### Scenario: server.py main() creates provider via factory

- GIVEN `server.py` `main()` function
- WHEN it initializes the MCP server
- THEN it MUST call the adapter factory to create a `CADProvider`
- AND it MUST pass the provider to `register_tools(mcp_instance, provider)`
- AND it MUST NOT instantiate `RealInventorDriver`, `DocumentManager`, etc. directly

#### Scenario: server.py has zero Inventor imports

- GIVEN `mcp_cad/server.py`
- WHEN all import statements are inspected
- THEN NO import path contains `mcp_cad.inventor` or `mcp_cad.providers`
- AND the ONLY mcp_cad imports are from `core.protocol`, `tools`, and `errors`

## MODIFIED Requirements

### Requirement: server.py register_tools Signature

The `register_tools` function signature changes from accepting 8 individual parameters (driver, doc_mgr, sketch_mgr, feature_mgr, param_mgr, prop_mgr, export_mgr) to accepting 2 parameters (mcp_instance, provider).

(Previously: `register_tools(mcp_instance, driver, doc_mgr, sketch_mgr, feature_mgr, param_mgr, prop_mgr, export_mgr)`)

#### Scenario: New signature is simpler

- GIVEN the new `register_tools` function
- WHEN called
- THEN it accepts exactly 2 positional parameters: `mcp_instance: FastMCP` and `provider: CADProvider`
- AND all tool closures capture the provider, not individual managers

#### Scenario: Backward compatibility shim exists during transition

- GIVEN Phase 4 implementation
- WHEN the old `register_tools` signature is used
- THEN a shim function MUST translate the old 8-parameter call to the new 2-parameter call
- AND the shim MUST be removed before the change is merged

## Non-Goals

- Adding new MCP tools — all 32 tools are preserved with identical signatures
- Changing tool parameter types or default values
- Modifying the `_ok()` or `_err()` helper functions — they remain unchanged
- Implementing tool caching or lazy registration
