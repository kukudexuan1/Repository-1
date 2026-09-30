# Tasks: Provider-Skills Arquitectura

## Review Workload Forecast

**Decision needed before apply: Yes** — this change exceeds 800 lines and needs chained PRs.
**Chained PRs recommended: Yes**
**Chain strategy: feature-branch-chain** — PRs target the feature branch, final PR merges to main.
**400-line budget risk: High** (estimated ~1050-1250 total changed lines)

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1100 (net: ~650 new, ~150 moved, ~300 modified) |
| 800-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (Phase 0) → PR 2 (Phase 1) → PR 3 (Phases 2-3) → PR 4 (Phases 4-5) → PR 5 (Phase 6) |
| Delivery strategy | auto-forecast |

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Fix 16 failing tests + edges bug in feature.py | PR 1 | Base=main. Standalone — all tests green after this. |
| 2 | Protocol + data models (core/) | PR 2 | Base=main. New code, no consumers yet. |
| 3 | Move inventor/ → providers/inventor/ + adapter | PR 3 | Base=PR-2. Import-only changes + new adapter file. |
| 4 | Generic tools/ + server rewrite + skills | PR 4 | Base=PR-3. Wire everything together, update server.py. |
| 5 | COM bridge investigation doc | PR 5 | Base=main or independent. Spike-only, no code changes. |

## Phase 0: Green Baseline (Fix failing tests + edges bug)

- [x] 0.1 Update `test_document.py`: change `Documents.Add` assertions from 2-arg to 3-arg calls matching `GetTemplateFile` pattern
- [x] 0.2 Update `test_feature.py`: fix `CreateExtrudeDefinition` second arg `0`→`20485` (4 tests)
- [x] 0.3 Update `test_feature.py`: fix `SetDistanceExtent` direction enum `20929`→`20993` (1 test)
- [x] 0.4 Update `test_feature.py`: rewrite fillet tests from `CreateFilletDefinition`+`Add`→`AddSimple` (3 tests)
- [x] 0.5 Update `test_feature.py`: rewrite chamfer tests from `CreateChamferDefinition`+`Add`→`AddUsingDistance` (3 tests)
- [x] 0.6 Fix `mcp_cad/inventor/feature.py`: fillet/chamfer respect `edges` parameter (parse into `EdgeCollection` instead of iterating ALL edges)

**Verification**: `pytest tests/ --tb=short -q` — all 201 tests pass. Dependencies: none.

## Phase 1: Protocol Definition

- [x] 1.1 Create `mcp_cad/core/__init__.py` — package init
- [x] 1.2 Create `mcp_cad/core/models.py` — `Point2D`, `Plane`, `ExtrudeDef`, `RevolveDef` dataclasses with validation
- [x] 1.3 Create `mcp_cad/core/protocol.py` — `CADProvider` typing.Protocol with all domain method signatures (connection, doc, sketch, feature, param, property, export)

**Verification**: `python -c "from mcp_cad.core.protocol import CADProvider"` succeeds. Dependencies: Phase 0.

## Phase 2: Provider Migration

- [x] 2.1 Create `mcp_cad/providers/__init__.py` — package init
- [x] 2.2 Create `mcp_cad/providers/inventor/__init__.py` — re-export managers + `InventorProvider`
- [x] 2.3 `git mv mcp_cad/inventor/client.py mcp_cad/providers/inventor/client.py` — zero logic change
- [x] 2.4 `git mv mcp_cad/inventor/document.py mcp_cad/providers/inventor/document.py`
- [x] 2.5 `git mv mcp_cad/inventor/sketch.py mcp_cad/providers/inventor/sketch.py`
- [x] 2.6 `git mv mcp_cad/inventor/feature.py mcp_cad/providers/inventor/feature.py`
- [x] 2.7 `git mv mcp_cad/inventor/parameter.py mcp_cad/providers/inventor/parameter.py`
- [x] 2.8 `git mv mcp_cad/inventor/property.py mcp_cad/providers/inventor/property.py`
- [x] 2.9 `git mv mcp_cad/inventor/export.py mcp_cad/providers/inventor/export.py`
- [x] 2.10 Update all internal imports in moved files: `from mcp_cad.inventor.client` → `from mcp_cad.providers.inventor.client`
- [x] 2.11 Update `tests/conftest.py` import paths for moved modules
- [x] 2.12 Add backward-compat imports in `mcp_cad/inventor/__init__.py` or remove old package

**Verification**: `pytest tests/ -q` — all 201 tests pass after import path updates. Dependencies: Phase 1.

## Phase 3: Protocol Adapters

- [x] 3.1 Create `mcp_cad/providers/inventor/adapter.py` — `InventorProvider` class implementing `CADProvider`, delegates to manager instances
- [x] 3.2 Add edge parsing helper `_parse_edge_indices(edges: str) -> list[int]` in adapter — DEFERRED: FeatureManager already has `_parse_edge_indices` and `_build_edge_collection`; adapter delegates directly to manager methods which handle edge parsing internally
- [x] 3.3 Implement `fillet()` in adapter: delegates directly to `FeatureManager.fillet()` which handles edge parsing internally
- [x] 3.4 Implement `chamfer()` in adapter same pattern
- [x] 3.5 Create `tests/test_adapter.py` — test `InventorProvider` delegates 1:1 to each manager with mocked managers (49 tests)
- [x] 3.6 Add `make_mock_provider()` factory to `tests/conftest.py`

**Verification**: `pytest tests/test_adapter.py -q` — all adapter delegation tests pass. Dependencies: Phase 2.

## Phase 4: Generic Tools + server.py Rewrite

- [x] 4.1 Create `mcp_cad/tools/__init__.py` — `register_tools(mcp, provider: CADProvider)` registering all 32 tools
- [x] 4.2 Create `mcp_cad/tools/connection.py` — `inventor_connect`, `inventor_health`, `inventor_disconnect` wrapping `provider`
- [x] 4.3 Create `mcp_cad/tools/documents.py` — `doc_open`, `doc_new_part`, `doc_new_assembly`, `doc_save`, `doc_save_as`, `doc_close`
- [x] 4.4 Create `mcp_cad/tools/sketches.py` — `sketch_create`, `sketch_line`, `sketch_circle`, `sketch_arc`, `sketch_rectangle`, `sketch_dimension`
- [x] 4.5 Create `mcp_cad/tools/features.py` — `extrude`, `revolve`, `fillet`, `chamfer`
- [x] 4.6 Create `mcp_cad/tools/parameters.py` — `param_list`, `param_get`, `param_set`, `param_set_expression`
- [x] 4.7 Create `mcp_cad/tools/properties.py` — `iproperty_get`, `iproperty_set`, `iproperty_summary`, `iproperty_custom_get`, `iproperty_custom_set`
- [x] 4.8 Create `mcp_cad/tools/export.py` — `export_step`, `export_stl`, `export_pdf`, `export_dxf`
- [x] 4.9 Rewrite `mcp_cad/server.py` — import `InventorProvider` from adapter factory, call `register_tools(mcp, provider)`
- [x] 4.10 Update `tests/test_server.py` — new `register_tools(mcp, provider)` signature, mock provider instead of 7 managers
- [x] 4.11 Remove old `register_tools` backward-compat shim (old signature removed entirely in rewrite)

**Verification**: `pytest tests/ -q` — 313 tests pass with new wiring. `server.py` has zero `mcp_cad.inventor.*` imports. Dependencies: Phase 3.

## Phase 5: Skills System

- [x] 5.1 Create `mcp_cad/skills/__init__.py` — `register_skills(mcp, provider)` function
- [x] 5.2 Create `mcp_cad/skills/base.py` — `Skill` base class with `provider` DI and `register(mcp)` method
- [x] 5.3 Create `mcp_cad/skills/drilling.py` — `crear_patron_taladros()` composing sketch→circle→extrude-cut
- [x] 5.4 Add `register_skills()` call to `server.py` after `register_tools()`
- [x] 5.5 Create `tests/test_skills.py` — mock provider, verify composition order

**Verification**: `pytest tests/test_skills.py -q` — skill operations verify composition chain. Dependencies: Phase 4.

## Phase 6: COM Bridge Investigation

- [x] 6.1 Create `docs/com-bridge-investigation.md` — document HoleFeatures API limitations
- [x] 6.2 Document CircularPatternFeatures API limitations
- [x] 6.3 Document ThreadFeatures API limitations
- [x] 6.4 Add `create_hole_via_extrude_cut()` helper in investigation doc (workaround using existing protocol ops)

**Verification**: Document exists covering all three feature APIs with workaround feasibility. Dependencies: none (can be done in parallel with any phase).
