# CAD Provider Protocol Specification

## Purpose

Defines the abstract `CADProvider` protocol and core data models that decouple `mcp-cad` from Autodesk Inventor. All MCP tools delegate to protocol interfaces, enabling swappable backends (FreeCAD, Onshape, etc.) without changing tool signatures.

## Requirements

### Requirement: CADProvider Abstract Protocol

The system SHALL define a `CADProvider` abstract protocol in `mcp_cad/core/protocol.py` that covers all operational domains: connection lifecycle, document management, sketch operations, 3D feature operations, parameter management, property management, and export.

#### Scenario: Protocol defines connection operations

- GIVEN a `CADProvider` abstract class
- WHEN a backend implements it
- THEN it MUST provide `connect()`, `disconnect()`, and `health()` methods returning `dict[str, Any]`
- AND the signatures MUST match the current `InventorDriver` ABC

#### Scenario: Protocol defines document operations

- GIVEN a `DocumentOps` protocol
- WHEN a backend implements it
- THEN it MUST provide `doc_open(path)`, `doc_new_part(template)`, `doc_new_assembly(template)`, `doc_save()`, `doc_save_as(path)`, `doc_close(save)` methods
- AND each method MUST return `dict[str, Any]` with the same envelope as current managers

#### Scenario: Protocol defines sketch operations

- GIVEN a `SketchOps` protocol
- WHEN a backend implements it
- THEN it MUST provide `sketch_create(plane)`, `sketch_line(x1,y1,x2,y2)`, `sketch_circle(cx,cy,radius)`, `sketch_arc(cx,cy,radius,start_angle,end_angle)`, `sketch_rectangle(x1,y1,x2,y2)`, `sketch_dimension(entity,value,position)` methods
- AND active sketch state SHALL be tracked via an `active_sketch` property on the protocol

#### Scenario: Protocol defines feature operations

- GIVEN a `FeatureOps` protocol
- WHEN a backend implements it
- THEN it MUST provide `extrude(profile,distance,direction,taper,operation)`, `revolve(profile,axis,angle,operation)`, `fillet(edges,radius,mode)`, `chamfer(edges,distance,mode)` methods
- AND each method MUST accept the same parameter types as current `FeatureManager`

#### Scenario: Protocol defines parameter operations

- GIVEN a `ParameterOps` protocol
- WHEN a backend implements it
- THEN it MUST provide `param_list(filter_pattern)`, `param_get(name)`, `param_set(name,value)`, `param_set_expression(name,expression)` methods

#### Scenario: Protocol defines property operations

- GIVEN a `PropertyOps` protocol
- WHEN a backend implements it
- THEN it MUST provide `iproperty_get(name,property_set)`, `iproperty_set(name,value,property_set)`, `iproperty_summary()`, `iproperty_custom_get(name)`, `iproperty_custom_set(name,value)` methods

#### Scenario: Protocol defines export operations

- GIVEN an `ExportOps` protocol
- WHEN a backend implements it
- THEN it MUST provide `export_step(path,options)`, `export_stl(path,options)`, `export_pdf(path,options)`, `export_dxf(path,options)` methods

### Requirement: Core Data Models

The system SHALL define provider-agnostic data models in `mcp_cad/core/models.py` for geometric primitives used across backends.

#### Scenario: 2D geometry models exist

- GIVEN the `mcp_cad/core/models.py` module
- WHEN a developer imports it
- THEN it MUST export `Point2D(x, y)`, `Line(x1,y1,x2,y2)`, `Circle(cx,cy,radius)`, `Arc(cx,cy,radius,start_angle,end_angle)`, `Rectangle(x1,y1,x2,y2)` dataclasses
- AND each model MUST be serializable to/from dict for MCP tool boundaries

#### Scenario: 3D feature definition models exist

- GIVEN the `mcp_cad/core/models.py` module
- WHEN a developer imports it
- THEN it MUST export `ExtrudeDef(profile, distance, direction, taper, operation)`, `RevolveDef(profile, axis, angle, operation)` dataclasses
- AND direction values MUST be restricted to `"positive"`, `"negative"`, `"both"`
- AND operation values MUST be restricted to `"new_body"`, `"join"`, `"cut"`, `"intersect"`

#### Scenario: Edge case — invalid direction rejected

- GIVEN an `ExtrudeDef` dataclass with validation
- WHEN constructed with `direction="sideways"`
- THEN it MUST raise `ValueError`

### Requirement: Error Hierarchy Remains Generic

The system SHALL keep the existing error hierarchy in `mcp_cad/errors.py` unchanged. Error names SHALL NOT reference "Inventor" in the protocol layer — they remain backend-agnostic.

#### Scenario: Existing errors are reusable

- GIVEN the current `errors.py` with `InventorError`, `InventorCOMError`, etc.
- WHEN the protocol layer is implemented
- THEN errors SHALL be renamed to generic equivalents (`CADError`, `CADConnectionError`, `CADDisconnectedError`, `CADCOMError`) OR the existing names SHALL be kept with a deprecation alias
- AND all existing tests MUST continue to pass without modification to import paths

#### Scenario: New backend raises same error types

- GIVEN a FreeCAD provider implementation
- WHEN a COM-equivalent error occurs
- THEN it MUST raise the same error type from `mcp_cad/errors.py`
- AND the MCP tool error handler MUST catch it identically

### Requirement: Provider Adapter Factory

The system SHALL provide an adapter factory function that constructs a concrete `CADProvider` from the Inventor backend managers.

#### Scenario: Factory creates Inventor provider

- GIVEN the adapter factory `create_inventor_provider()`
- WHEN called with no arguments
- THEN it MUST return a `CADProvider` implementation backed by `RealInventorDriver`, `DocumentManager`, `SketchManager`, `FeatureManager`, `ParameterManager`, `PropertyManager`, `ExportManager`
- AND the returned provider MUST implement 100% of the protocol

#### Scenario: Factory is the only Inventor import in server.py

- GIVEN `mcp_cad/server.py`
- WHEN it needs a provider
- THEN it MUST import ONLY from `mcp_cad.core.protocol` and the adapter factory
- AND it MUST NOT import any `mcp_cad.inventor.*` or `mcp_cad.providers.*` modules directly

## Non-Goals

- Implementing additional CAD backends (FreeCAD, Onshape) — only the protocol is defined
- Changing any MCP tool signatures — all signatures are preserved
- Modifying COM enumeration constants — they stay in the Inventor provider layer
