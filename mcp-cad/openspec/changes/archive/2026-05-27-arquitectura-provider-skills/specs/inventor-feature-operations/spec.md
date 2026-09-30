# Inventor Feature Operations — Delta Spec

## ADDED Requirements

### Requirement: Fillet/Chamfer Edges Parameter Respected

The system MUST apply the `edges` parameter passed to `fillet()` and `chamfer()` instead of ignoring it and applying to ALL edges of the first surface body.

#### Scenario: Fillet applies to specified edges only

- GIVEN an active part document with a body that has 12 edges
- WHEN `fillet(edges="edge_ref", radius=2.5)` is called with a specific edge reference
- THEN ONLY the specified edge(s) receive the fillet
- AND the return dict MUST include `"edges_applied": <count>` metadata

#### Scenario: Chamfer applies to specified edges only

- GIVEN an active part document with a body that has 12 edges
- WHEN `chamfer(edges="edge_ref", distance=1.5)` is called with a specific edge reference
- THEN ONLY the specified edge(s) receive the chamfer
- AND the return dict MUST include `"edges_applied": <count>` metadata

#### Scenario: Fillet with no specific edges defaults to all

- GIVEN an active part document
- WHEN `fillet(edges=None, radius=2.5)` is called (or edges parameter is empty)
- THEN the fillet applies to ALL edges of the first surface body (current behavior preserved as fallback)

### Requirement: Inventor 2025+ Enum Values Hard-Coded in Provider Only

The system SHALL hard-code all Inventor 2025+ COM enumeration values inside the Inventor provider module (`mcp_cad/providers/inventor/feature.py`), NOT in the protocol or adapter layer.

#### Scenario: Enum values are provider-internal

- GIVEN the protocol layer `mcp_cad/core/protocol.py`
- WHEN a backend implements `FeatureOps`
- THEN it MUST NOT expose COM enumeration constants in the protocol
- AND string values like `"new_body"`, `"positive"`, `"constant"` are the ONLY public interface

## MODIFIED Requirements

### Requirement: Fillet Uses AddSimple API (Inventor 2025+)

The fillet operation MUST use `FilletFeatures.AddSimple(edge_collection, radius)` for constant-radius fillets. The `edges` parameter MUST be used to build the edge collection, not ignored.

(Previously: edges parameter was ignored; ALL edges of first surface body were always filleted)

#### Scenario: Fillet with specific edge reference

- GIVEN a `FeatureManager` with an active document
- WHEN `fillet(edges=com_edge_object, radius=2.5)` is called
- THEN `TransientObjects.CreateEdgeCollection()` is created
- AND the specified `com_edge_object` is added to the collection
- AND `FilletFeatures.AddSimple(edge_col, 2.5)` is called with that collection

#### Scenario: Fillet with string edge name

- GIVEN a `FeatureManager` with an active document
- WHEN `fillet(edges="Edge1", radius=2.5)` is called
- THEN the string is resolved to a COM edge reference
- AND only that edge is added to the edge collection
- AND `AddSimple` is called with the single-edge collection

### Requirement: Chamfer Uses Convenience Methods (Inventor 2025+)

The chamfer operation MUST use `ChamferFeatures.AddUsingDistance(edge_collection, distance)` or `AddUsingTwoDistances(edge_collection, d1, d2)`. The `edges` parameter MUST be used to build the edge collection.

(Previously: edges parameter was ignored; ALL edges of first surface body were always chamfered)

#### Scenario: Chamfer equal_distance with specific edges

- GIVEN a `FeatureManager` with an active document
- WHEN `chamfer(edges=com_edge_object, distance=1.5, mode="equal_distance")` is called
- THEN an EdgeCollection is built containing ONLY the specified edge(s)
- AND `ChamferFeatures.AddUsingDistance(edge_col, 1.5)` is called

#### Scenario: Chamfer two_distances with specific edges

- GIVEN a `FeatureManager` with an active document
- WHEN `chamfer(edges=com_edge_object, distance=1.5, mode="two_distances")` is called
- THEN `ChamferFeatures.AddUsingTwoDistances(edge_col, 1.5, 1.5)` is called with only the specified edges

### Requirement: Test Assertions Use Inventor 2025+ Enum Values

All test assertions in `test_feature.py` MUST use the Inventor 2025+ enumeration values (e.g., `20485` for `kNewBodyOperation`, `20993` for `kPositiveExtentDirection`) instead of legacy values (e.g., `0`, `20929`).

(Previously: tests used legacy enum values that no longer match Inventor 2025+ API)

#### Scenario: Extrude test uses 2025+ operation enum

- GIVEN `test_extrude_success` in `test_feature.py`
- WHEN the test asserts on `CreateExtrudeDefinition` call arguments
- THEN the second argument MUST be `20485` (kNewBodyOperation), NOT `0`

#### Scenario: Extrude test uses 2025+ direction enum

- GIVEN `test_extrude_success` in `test_feature.py`
- WHEN the test asserts on `SetDistanceExtent` call arguments
- THEN the direction argument MUST be `20993` (kPositiveExtentDirection), NOT `20929`

#### Scenario: Fillet test uses AddSimple pattern

- GIVEN `test_fillet_success` in `test_feature.py`
- WHEN the test verifies fillet creation
- THEN it MUST assert `FilletFeatures.AddSimple` was called, NOT `CreateFilletDefinition` + `Add`
- AND the `edges` parameter MUST be verified as used in the edge collection

#### Scenario: Chamfer test uses AddUsingDistance pattern

- GIVEN `test_chamfer_success` in `test_feature.py`
- WHEN the test verifies chamfer creation
- THEN it MUST assert `ChamferFeatures.AddUsingDistance` was called, NOT `CreateChamferDefinition` + `Add`

## REMOVED Requirements

### Requirement: Fillet/Chamfer Variable Mode Support

(Reason: Inventor 2025+ API does not support variable-radius fillets through the new `AddSimple` method; only constant-radius is available. The `mode` parameter accepts only `"constant"` for fillets.)

### Requirement: Legacy CreateFilletDefinition / CreateChamferDefinition Pattern

(Reason: Inventor 2025+ replaces the two-step `CreateXxxDefinition` + `Add` pattern with direct convenience methods `AddSimple`, `AddUsingDistance`, `AddUsingTwoDistances`.)

## Non-Goals

- Adding support for variable-radius fillets — out of scope for Inventor 2025+ API
- Implementing edge name resolution from string — COM edge references are passed directly
- Changing the fillet/chamfer MCP tool signatures — `edges`, `radius`/`distance`, `mode` remain the same
