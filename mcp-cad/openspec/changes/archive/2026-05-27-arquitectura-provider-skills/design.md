# Design: arquitectura-provider-skills

## Technical Approach

Six-phase refactor decouples `server.py` from Inventor COM via a `CADProvider` protocol. Inventor managers move to `mcp_cad/providers/inventor/` unchanged; thin protocol adapters expose them generically. Generic tools in `mcp_cad/tools/` receive a `CADProvider` instance, making `server.py` backend-agnostic. Skills compose provider operations directly.

## Architecture Decisions

| Decision | Option A (chosen) | Option B (rejected) | Rationale |
|---|---|---|---|
| Protocol style | `typing.Protocol` with runtime-checkable methods | Full ABC with `@abstractmethod` | Protocols are lighter; adapters can be dataclasses or plain objects without inheritance boilerplate |
| Adapter granularity | One `InventorProvider` adapter wrapping all managers | One adapter per manager domain | Fewer objects to wire in `server.py`; managers already split by domain |
| Sketch state | Adapter holds `_active_sketch` reference | Protocol requires stateless ops | Matches existing `SketchManager._active_sketch` behavior; Inventor requires an active sketch context |
| Edge parsing | Parse comma-separated indices in adapter, build `EdgeCollection` | Push parsing to tool layer | Keeps tools generic; Inventor-specific edge semantics stay in provider |
| Tool registration | `register_tools(mcp, provider)` | Keep per-manager registration | Simplifies server wiring; tools call `provider.extrude()` etc. |

## Data Flow

    MCP Tool call
         |
    mcp_cad/tools/*.py  ──→  CADProvider protocol method
         |                          |
    InventorProvider  ────→  Inventor*Manager (COM)
         |                          |
    Return {success, data} ←──  COM result / exception

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `mcp_cad/core/__init__.py` | Create | Package init |
| `mcp_cad/core/protocol.py` | Create | `CADProvider` Protocol + data models |
| `mcp_cad/core/models.py` | Create | `Point2D`, `Plane`, `ExtrudeDef`, etc. |
| `mcp_cad/providers/__init__.py` | Create | Package init |
| `mcp_cad/providers/inventor/__init__.py` | Create | Re-exports `InventorProvider`, `RealInventorDriver` |
| `mcp_cad/providers/inventor/client.py` | Move | From `mcp_cad/inventor/client.py` (zero logic change) |
| `mcp_cad/providers/inventor/document.py` | Move | From `mcp_cad/inventor/document.py` (zero logic change) |
| `mcp_cad/providers/inventor/sketch.py` | Move | From `mcp_cad/inventor/sketch.py` (zero logic change) |
| `mcp_cad/providers/inventor/feature.py` | Move | From `mcp_cad/inventor/feature.py` (zero logic change) |
| `mcp_cad/providers/inventor/parameter.py` | Move | From `mcp_cad/inventor/parameter.py` (zero logic change) |
| `mcp_cad/providers/inventor/property.py` | Move | From `mcp_cad/inventor/property.py` (zero logic change) |
| `mcp_cad/providers/inventor/export.py` | Move | From `mcp_cad/inventor/export.py` (zero logic change) |
| `mcp_cad/providers/inventor/adapter.py` | Create | `InventorProvider` protocol adapter |
| `mcp_cad/tools/__init__.py` | Create | Generic tool registration `register_tools(mcp, provider)` |
| `mcp_cad/tools/connection.py` | Create | `inventor_connect`, `inventor_health`, `inventor_disconnect` |
| `mcp_cad/tools/document.py` | Create | `doc_open`, `doc_new_part`, etc. |
| `mcp_cad/tools/sketch.py` | Create | `sketch_create`, `sketch_line`, etc. |
| `mcp_cad/tools/feature.py` | Create | `extrude`, `revolve`, `fillet`, `chamfer` |
| `mcp_cad/tools/parameter.py` | Create | `param_list`, `param_get`, etc. |
| `mcp_cad/tools/property.py` | Create | `iproperty_get`, `iproperty_set`, etc. |
| `mcp_cad/tools/export.py` | Create | `export_step`, `export_stl`, etc. |
| `mcp_cad/skills/__init__.py` | Create | Package init |
| `mcp_cad/skills/drilling.py` | Create | `crear_patron_taladros` skill |
| `mcp_cad/server.py` | Modify | Imports `CADProvider` + `InventorProvider`; calls generic `register_tools` |
| `tests/test_document.py` | Modify | Update 4 assertions for `GetTemplateFile` + 3-arg `Add` |
| `tests/test_feature.py` | Modify | Update 5 extrude enum assertions; update 3 fillet + 3 chamfer assertions for `AddSimple`/`AddUsingDistance`; fix `edges` tests; update 1 profile resolution assertion |
| `tests/test_server.py` | Modify | Update `register_tools` signature to `(mcp, provider)` |
| `tests/conftest.py` | Modify | Update import paths; add `make_mock_provider()` factory |

## Interfaces / Contracts

```python
from typing import Protocol, Any
from enum import Enum

class Plane(str, Enum):
    XY = "XY"
    XZ = "XZ"
    YZ = "YZ"

class Point2D:
    x: float
    y: float

class CADProvider(Protocol):
    # Connection
    def connect(self) -> dict[str, Any]: ...
    def disconnect(self) -> dict[str, Any]: ...
    def health(self) -> dict[str, Any]: ...

    # Documents
    def doc_open(self, path: str) -> dict[str, Any]: ...
    def doc_new_part(self, template: str = "") -> dict[str, Any]: ...
    def doc_new_assembly(self, template: str = "") -> dict[str, Any]: ...
    def doc_save(self) -> dict[str, Any]: ...
    def doc_save_as(self, path: str) -> dict[str, Any]: ...
    def doc_close(self, save: bool = True) -> dict[str, Any]: ...

    # Sketches
    def sketch_create(self, plane: str = "XY") -> dict[str, Any]: ...
    def sketch_line(self, x1: float, y1: float, x2: float, y2: float) -> dict[str, Any]: ...
    def sketch_circle(self, cx: float, cy: float, radius: float) -> dict[str, Any]: ...
    def sketch_arc(self, cx: float, cy: float, radius: float, start_angle: float, end_angle: float) -> dict[str, Any]: ...
    def sketch_rectangle(self, x1: float, y1: float, x2: float, y2: float) -> dict[str, Any]: ...
    def sketch_dimension(self, entity: str, value: float, position: tuple[float, float] | None = None) -> dict[str, Any]: ...

    # Features
    def extrude(self, profile: str, distance: float, direction: str = "positive", taper: float = 0.0, operation: str = "new_body") -> dict[str, Any]: ...
    def revolve(self, profile: str, axis: str, angle: float = 360.0, operation: str = "join") -> dict[str, Any]: ...
    def fillet(self, edges: str, radius: float, mode: str = "constant") -> dict[str, Any]: ...
    def chamfer(self, edges: str, distance: float, mode: str = "equal_distance") -> dict[str, Any]: ...

    # Parameters
    def param_list(self, filter_pattern: str | None = None) -> dict[str, Any]: ...
    def param_get(self, name: str) -> dict[str, Any]: ...
    def param_set(self, name: str, value: float) -> dict[str, Any]: ...
    def param_set_expression(self, name: str, expression: str) -> dict[str, Any]: ...

    # Properties
    def iproperty_get(self, name: str, property_set: str = "Summary") -> dict[str, Any]: ...
    def iproperty_set(self, name: str, value: Any, property_set: str = "Summary") -> dict[str, Any]: ...
    def iproperty_summary(self) -> dict[str, Any]: ...
    def iproperty_custom_get(self, name: str) -> dict[str, Any]: ...
    def iproperty_custom_set(self, name: str, value: Any) -> dict[str, Any]: ...

    # Export
    def export_step(self, path: str, options: dict[str, Any] | None = None) -> dict[str, Any]: ...
    def export_stl(self, path: str, options: dict[str, Any] | None = None) -> dict[str, Any]: ...
    def export_pdf(self, path: str, options: dict[str, Any] | None = None) -> dict[str, Any]: ...
    def export_dxf(self, path: str, options: dict[str, Any] | None = None) -> dict[str, Any]: ...
```

**Adapter skeleton** (`adapter.py`):
```python
class InventorProvider:
    def __init__(self, driver: RealInventorDriver) -> None:
        self._driver = driver
        self._doc = DocumentManager(driver)
        self._sketch = SketchManager(driver)
        self._feature = FeatureManager(driver)
        self._param = ParameterManager(driver)
        self._prop = PropertyManager(driver)
        self._export = ExportManager(driver)

    def connect(self) -> dict[str, Any]: return self._driver.connect()
    # ... delegates for all protocol methods ...
    def sketch_create(self, plane: str = "XY") -> dict[str, Any]:
        return self._sketch.sketch_create(plane)
    # sketch_line, etc. pass through directly
    def fillet(self, edges: str, radius: float, mode: str = "constant") -> dict[str, Any]:
        # Parse edges string "1,3,5" into EdgeCollection via TransientObjects
        edge_col = self._driver.inventor.TransientObjects.CreateEdgeCollection()
        sb = self._driver.inventor.ActiveDocument.ComponentDefinition.SurfaceBodies.Item(1)
        for idx in _parse_edge_indices(edges):
            edge_col.Add(sb.Edges.Item(idx))
        return self._feature.fillet(edge_col, radius, mode)
```

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit — managers | Existing manager logic after move | Keep all 185 passing tests; update 16 failing assertions to match Inventor 2025+ API |
| Unit — adapter | `InventorProvider` delegates correctly | New `test_adapter.py` with mocked managers; verify each protocol method delegates 1:1 |
| Unit — tools | Generic tool functions call provider | New `test_tools.py` with a mock `CADProvider`; verify arguments pass through |
| Unit — skills | `crear_patron_taladros` chains ops | New `test_skills.py` with mock provider; assert sketch → circle → extrude-cut sequence |
| Integration | `server.py` registration | Update `test_server.py` to use new `register_tools(mcp, provider)` signature |

## Migration / Rollout

Six commits, each leaving tests green:

1. **Phase 0 — Fix 16 failing tests**: Update assertions in `test_document.py` (4), `test_feature.py` (11), `test_parameter.py` (1). Fix `feature.py` fillet/chamfer to parse `edges` parameter instead of using ALL edges.
2. **Phase 1 — Protocol + models**: Create `mcp_cad/core/protocol.py` and `mcp_cad/core/models.py`. No production consumers yet.
3. **Phase 2 — Move Inventor files**: `git mv mcp_cad/inventor/* mcp_cad/providers/inventor/`. Update all internal imports. Update `conftest.py` `sys.modules` paths atomically. Zero logic changes.
4. **Phase 3 — Build adapter**: Create `mcp_cad/providers/inventor/adapter.py` implementing `CADProvider`. Add `test_adapter.py`.
5. **Phase 4 — Generic tools + server rewrite**: Create `mcp_cad/tools/` modules. Rewrite `server.py` to import `InventorProvider` and call generic `register_tools(mcp, provider)`. Update `test_server.py`.
6. **Phase 5+6 — Skills + COM bridge**: Add `mcp_cad/skills/drilling.py`. Add investigation doc for HoleFeatures / CircularPatternFeatures / ThreadFeatures.

## Import Graph

```
server.py
  └─ mcp_cad.tools.register_tools
       └─ CADProvider (protocol)
            └─ InventorProvider ← mcp_cad.providers.inventor.adapter
                 └─ RealInventorDriver, DocumentManager, SketchManager, …

skills/*.py
  └─ CADProvider (protocol only — no tools, no managers)
```

No circular dependencies: `core` has no imports from `providers` or `tools`. `skills` depends only on `core.protocol`.

## Skills Example

```python
# mcp_cad/skills/drilling.py
from mcp_cad.core.protocol import CADProvider

def crear_patron_taladros(
    provider: CADProvider,
    diametro: float,
    profundidad: float,
    espaciado: float,
    cantidad: int,
) -> dict:
    """Create a linear hole pattern by sketching circles and extrude-cutting."""
    provider.sketch_create("XY")
    for i in range(cantidad):
        x = i * espaciado
        provider.sketch_circle(x, 0.0, diametro / 2)
    provider.extrude("all_profiles", profundidad, operation="cut")
    return {"success": True, "holes": cantidad, "diameter": diametro}
```

Skills register as regular MCP tools in `server.py` and receive the active provider.

## Open Questions

- [ ] Should `Plane` be a `str` or `Enum` in the protocol? `Enum` is safer; existing code uses string lookup.
- [ ] Edge parsing: support `"edge:1"` syntax in addition to comma indices? Deferred to Phase 0 minimal fix.
- [ ] COM bridge: HoleFeatures investigation may reveal we need a `hole()` protocol method; out of scope for this change.
