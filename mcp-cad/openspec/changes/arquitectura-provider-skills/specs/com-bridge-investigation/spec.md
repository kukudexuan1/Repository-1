# COM Bridge Investigation Specification

## Purpose

Documents the investigation of COM bridge limitations for advanced Inventor features (HoleFeatures, CircularPatternFeatures, ThreadFeatures) and provides workaround helpers where feasible.

## Requirements

### Requirement: Investigation Document

The system SHALL produce an investigation document at `docs/com-bridge-investigation.md` that covers:

- HoleFeatures API availability and limitations
- CircularPatternFeatures API availability and limitations
- ThreadFeatures API availability and limitations
- What works, what's blocked, and why

#### Scenario: Investigation covers HoleFeatures

- GIVEN the investigation document
- WHEN the HoleFeatures section is reviewed
- THEN it MUST document:
  - Whether `HoleFeatures.CreateHoleDefinition` is accessible via late-bound COM
  - Any errors encountered (e.g., `AttributeError`, `COMError`)
  - Workaround feasibility (extrude-cut as alternative)

#### Scenario: Investigation covers CircularPatternFeatures

- GIVEN the investigation document
- WHEN the CircularPatternFeatures section is reviewed
- THEN it MUST document:
  - Whether circular patterns are creatable via COM bridge
  - Any enumeration or parameter issues
  - Workaround feasibility (manual placement via loop)

#### Scenario: Investigation covers ThreadFeatures

- GIVEN the investigation document
- WHEN the ThreadFeatures section is reviewed
- THEN it MUST document:
  - Whether thread features are creatable via COM bridge
  - Any type library or early-binding requirements
  - Workaround feasibility (cosmetic representation or skip)

### Requirement: Workaround Helper for Holes

The system SHALL provide a `create_hole_via_extrude_cut(provider, position, diameter, depth)` helper function that creates a hole using extrude-cut instead of HoleFeatures.

#### Scenario: Hole workaround creates sketch circle and cuts

- GIVEN an active part document with a planar face
- WHEN `create_hole_via_extrude_cut` is called with position, diameter, depth
- THEN it MUST:
  1. Create a sketch on the target face
  2. Draw a circle at the specified position
  3. Extrude-cut the circle to the specified depth
  4. Return `{"success": True, "hole_diameter": diameter, "depth": depth}`

#### Scenario: Hole workaround validates inputs

- GIVEN the `create_hole_via_extrude_cut` helper
- WHEN called with `diameter <= 0` or `depth <= 0`
- THEN it MUST raise `ValueError` with a descriptive message

### Requirement: Investigation Is Spike-Only

The investigation SHALL NOT attempt to fix COM bridge issues. It documents what is blocked and provides workarounds only where feasible with existing protocol operations.

#### Scenario: Investigation does not modify COM behavior

- GIVEN the investigation scope
- WHEN reviewing the deliverables
- THEN no changes to `pywin32`, COM dispatch, or Inventor type library bindings are included
- AND all workarounds use existing protocol operations (sketch + extrude-cut)

## Non-Goals

- Fixing HoleFeatures, CircularPatternFeatures, or ThreadFeatures COM bridge issues
- Implementing early-bound COM dispatch (gencache) — late-bound only
- Adding new COM enumeration constants beyond what's already in feature.py
- Creating a full hole table or pattern library — only a single helper function
