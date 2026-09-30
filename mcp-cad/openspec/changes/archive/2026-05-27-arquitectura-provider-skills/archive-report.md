# Archive Report: arquitectura-provider-skills

**Archived**: 2026-05-27
**Branch**: `feature/arquitectura-provider-skills`
**Original location**: `openspec/changes/arquitectura-provider-skills/`
**Archive location**: `openspec/changes/archive/2026-05-27-arquitectura-provider-skills/`

## Executive Summary

Six-phase architecture refactor decoupling mcp-cad from Autodesk Inventor via a `CADProvider` protocol. The change introduced a provider-based architecture with abstract protocol definitions, Inventor-specific provider migration, protocol adapters, generic MCP tool registration, and a composable skills layer. All 313 tests pass, the critical `sketch_dimension` position bug is fixed, and no CRITICAL issues remain.

**Verdict**: PASS WITH WARNINGS (3 non-blocking warnings)

## Engram Artifacts (observation IDs)

| Artifact | Observation ID | Topic Key |
|----------|---------------|-----------|
| Proposal | #108 | `sdd/arquitectura-provider-skills/proposal` |
| Spec | #109 | `sdd/arquitectura-provider-skills/spec` |
| Design | #110 | `sdd/arquitectura-provider-skills/design` |
| Tasks | #111 | `sdd/arquitectura-provider-skills/tasks` |
| Apply Progress | #112 | `sdd/arquitectura-provider-skills/apply-progress` |
| Verify Report | #119 | `sdd/arquitectura-provider-skills/verify-report` |
| Archive Report | (current) | `sdd/arquitectura-provider-skills/archive-report` |

## Filesystem Artifacts

- `proposal.md` ✅ (32 lines)
- `specs/cad-provider-protocol/spec.md` ✅ (124 lines)
- `specs/inventor-feature-operations/spec.md` ✅ (128 lines)
- `specs/mcp-tool-registration/spec.md` ✅ (120 lines)
- `specs/skills-composition/spec.md` ✅ (107 lines)
- `specs/com-bridge-investigation/spec.md` ✅ (81 lines)
- `design.md` ✅ (213 lines)
- `tasks.md` ✅ (108 lines, 32/32 tasks complete)
- `verify-report.md` ✅ (202 lines)
- `archive-report.md` ✅ (current)

## Summary of What Was Done

### Phase 0: Green Baseline
- Fixed 16 failing tests (outdated enum assertions + old API patterns)
- Fixed fillet/chamfer `edges` parameter bug (was ignoring parameter, applying to ALL edges)

### Phase 1: Protocol Definition
- Created `mcp_cad/core/protocol.py` — `CADProvider` typing.Protocol with 32 methods
- Created `mcp_cad/core/models.py` — `Point2D`, `Plane`, `ExtrudeDef`, etc.

### Phase 2: Provider Migration
- Moved `mcp_cad/inventor/*` → `mcp_cad/providers/inventor/*` (zero logic change)
- Updated all internal imports and test conftest paths

### Phase 3: Protocol Adapters
- Created `mcp_cad/providers/inventor/adapter.py` — `InventorProvider` implementing `CADProvider`
- 49 adapter delegation tests

### Phase 4: Generic Tools + server.py Rewrite
- Created 7 tool modules under `mcp_cad/tools/` with 32 tools
- Rewrote `server.py` to import only protocol + factory
- Zero imports from `mcp_cad.inventor.*` or `mcp_cad.providers.*` in tools/skills/core

### Phase 5: Skills System
- Created `mcp_cad/skills/` with Skill base class + `crear_patron_taladros` drilling skill
- Skills are provider-agnostic, import from protocol only

### Phase 6: COM Bridge Investigation
- Created `docs/com-bridge-investigation.md` (409 lines)
- Documented HoleFeatures, CircularPatternFeatures, ThreadFeatures limitations
- Provided `create_hole_via_extrude_cut` workaround

## Architectural Decisions

| Decision | Chosen Approach | Rationale |
|----------|----------------|-----------|
| Protocol style | `typing.Protocol` with `@runtime_checkable` | Lighter than ABC, adapters need no inheritance |
| Adapter granularity | Single `InventorProvider` wrapping all managers | Fewer wiring objects in server.py |
| Sketch state | Adapter holds `_active_sketch` reference | Matches existing SketchManager behavior |
| Edge parsing | Comma-separated indices → `EdgeCollection` in FeatureManager | Keeps tools generic |
| Tool registration | `register_tools(mcp, provider)` | Single 2-param function vs 8 params |

## Files Changed (from design doc)

**Created**:
- `mcp_cad/core/__init__.py`, `mcp_cad/core/protocol.py`, `mcp_cad/core/models.py`
- `mcp_cad/providers/__init__.py`, `mcp_cad/providers/inventor/__init__.py`, `mcp_cad/providers/inventor/adapter.py`
- `mcp_cad/tools/__init__.py`, `mcp_cad/tools/connection.py`, `mcp_cad/tools/documents.py`, `mcp_cad/tools/sketches.py`, `mcp_cad/tools/features.py`, `mcp_cad/tools/parameters.py`, `mcp_cad/tools/properties.py`, `mcp_cad/tools/export.py`
- `mcp_cad/skills/__init__.py`, `mcp_cad/skills/base.py`, `mcp_cad/skills/drilling.py`
- `tests/test_adapter.py`, `tests/test_tools.py`, `tests/test_skills.py`
- `docs/com-bridge-investigation.md`

**Moved** (zero logic change):
- `mcp_cad/inventor/client.py` → `mcp_cad/providers/inventor/client.py`
- `mcp_cad/inventor/document.py` → `mcp_cad/providers/inventor/document.py`
- `mcp_cad/inventor/sketch.py` → `mcp_cad/providers/inventor/sketch.py`
- `mcp_cad/inventor/feature.py` → `mcp_cad/providers/inventor/feature.py`
- `mcp_cad/inventor/parameter.py` → `mcp_cad/providers/inventor/parameter.py`
- `mcp_cad/inventor/property.py` → `mcp_cad/providers/inventor/property.py`
- `mcp_cad/inventor/export.py` → `mcp_cad/providers/inventor/export.py`

**Modified**:
- `mcp_cad/server.py` — rewrite to use protocol
- `mcp_cad/inventor/feature.py` — fix fillet/chamfer edges bug
- `tests/test_document.py`, `tests/test_feature.py`, `tests/test_server.py`, `tests/test_parameter.py`, `tests/conftest.py`

## Source of Truth Updated

The following main specs now reflect the new behavior:
- `openspec/specs/cad-provider-protocol/spec.md` — Created (new domain)
- `openspec/specs/inventor-feature-operations/spec.md` — Created (new domain)
- `openspec/specs/mcp-tool-registration/spec.md` — Created (new domain)
- `openspec/specs/skills-composition/spec.md` — Created (new domain)
- `openspec/specs/com-bridge-investigation/spec.md` — Created (new domain)

## Remaining Warnings (non-blocking)

1. **pyproject.toml diff**: Uncommitted `tui = ["prompt_toolkit>=3.0"]` optional dependency — out of scope, commit or revert separately.
2. **Spec contradiction**: `cad-provider-protocol` spec has conflicting scenarios about server.py imports. Implementation follows the more specific scenario correctly.
3. **Spec mentions non-existent `active_sketch` property**: Protocol has no such property (correctly delegated to SketchManager). Spec should be updated.

## Next Recommended

1. Commit or revert the unrelated `pyproject.toml` diff
2. Fix the 2 spec documentation inconsistencies in `cad-provider-protocol/spec.md`
3. Merge `feature/arquitectura-provider-skills` to main
4. Consider a follow-up change to address the 4 SUGGESTIONS (coverage, `__main__.py`, naming consistency, error hierarchy aliases)
