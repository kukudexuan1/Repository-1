# Proposal: arquitectura-provider-skills

## Intent

Decouple mcp-cad from Autodesk Inventor by introducing a provider-based architecture and a composable skills layer. Today, `server.py` imports concrete Inventor managers directly, making the codebase vendor-locked and untestable without COM mocks. This refactor enables multi-CAD backends, cleaner testing, and higher-level reusable operations.

## Scope

### In Scope
- Abstract `CADProvider` protocol in `mcp_cad/core/protocol.py`
- Move Inventor COM code to `mcp_cad/providers/inventor/`
- Protocol adapters wiring Inventor managers to the generic protocol
- Generic `register_tools()` depending on protocol ABCs only
- Skills system in `mcp_cad/skills/` with composable operations
- Fix 16 failing tests (outdated enum assertions, old API patterns)
- Fix fillet/chamfer `edges` parameter bug

### Out of Scope
- New CAD backends (e.g., FreeCAD) — only Inventor in this change
- New MCP tools beyond current set
- COM bridge fixes for unimplemented features (HoleFeatures, etc.) — investigated but not fixed

## Capabilities

### New Capabilities
- `cad-provider-protocol`: Abstract `CADProvider`, `DocumentOps`, `SketchOps`, `FeatureOps`, `ParameterOps`, `PropertyOps`, `ExportOps`
- `skills-composition`: Skill base class and example composed operations

### Modified Capabilities
- `inventor-feature-operations`: Fix `edges` parameter handling in fillet/chamfer; update enum values to Inventor 2025+
- `mcp-tool-registration`: Rewrite `server.py` to depend on protocol instead of concrete managers

## Approach

Six phases, each leaving tests green:

| Phase | Task | Risk |
|---|---|---|
| 0 | Fix 16 failing tests + fillet/chamfer `edges` bug | Low |
| 1 | Define protocol ABCs in `mcp_cad/core/protocol.py` | None (new code) |
| 2 | Move `mcp_cad/inventor/*` → `mcp_cad/providers/inventor/*` | Low (mechanical) |
| 3 | Build protocol adapters over Inventor managers | Med |
| 4 | Rewrite `server.py` to use protocol + adapters | Med |
| 5 | Add skills system (`mcp_cad/skills/`) | Low |
| 6 | Investigate COM bridge issues (HoleFeatures, etc.) | Low (spike only) |

## Directory Structure

```
mcp_cad/
├── core/
│   └── protocol.py          # CADProvider ABCs
├── providers/
│   └── inventor/
│       ├── __init__.py
│       ├── client.py        # RealInventorDriver
│       ├── document.py
│       ├── sketch.py
│       ├── feature.py
│       ├── parameter.py
│       ├── property.py
│       ├── export.py
│       └── adapter.py       # Protocol adapters
├── skills/
│   ├── __init__.py
│   └── base.py              # Skill base + examples
├── tools/
│   └── __init__.py          # Generic tool registration
├── server.py                # Depends on protocol only
└── errors.py                # Unchanged
```

## API Surface

| Consumer | Before | After |
|---|---|---|
| `server.py` | Imports `RealInventorDriver`, `DocumentManager`, etc. | Imports `CADProvider` protocol + adapter factory |
| Tests | Test concrete managers directly | Add protocol adapter tests; keep manager tests |
| End users | Same MCP tool names and signatures | Unchanged |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Test regression during move | Med | Phase 0 first; move with zero logic changes |
| `conftest.py` mock breakage | Med | Update `sys.modules` paths atomically with file moves |
| Active sketch state lost in abstraction | Low | Keep state in adapter layer, expose via protocol property |
| Enum value drift | Low | Hard-code Inventor 2025+ values in provider only |

## Rollback Plan

Revert any phase via git revert. Phases 1-2 are additive/mechanical and trivially reversible. Phase 4 keeps old `register_tools` signature behind a shim until verified.

## Dependencies

- `pytest` for test verification after each phase
- `pywin32` / COM environment for integration smoke tests (optional)

## Success Criteria

- [ ] All 201 tests pass (185 existing + 16 fixed)
- [ ] `server.py` has zero imports from `mcp_cad.inventor.*`
- [ ] `mcp_cad.providers.inventor.adapter` implements 100 % of protocol
- [ ] At least one composed skill demonstrates chaining sketch → extrude → fillet
- [ ] HoleFeatures / CircularPatternFeatures / ThreadFeatures investigation doc exists
