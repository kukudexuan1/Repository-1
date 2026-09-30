# Skills Composition Specification

## Purpose

Defines a composable skills system in `mcp_cad/skills/` that provides higher-level MCP tools built by chaining atomic protocol operations. Skills are provider-agnostic — they work with any `CADProvider` implementation.

## Requirements

### Requirement: Skill Base Class

The system SHALL define a `Skill` base class in `mcp_cad/skills/base.py` that provides:

- A `provider: CADProvider` dependency injection point
- A `register(mcp_instance: FastMCP)` method to expose the skill as an MCP tool
- A `_ok(data)` / `_err(exc)` helper pattern consistent with server.py

#### Scenario: Skill base accepts provider

- GIVEN a subclass of `Skill`
- WHEN instantiated with `provider=my_provider`
- THEN the provider is stored as `self.provider`
- AND all skill methods delegate to `self.provider` operations

#### Scenario: Skill registers as MCP tool

- GIVEN a `DrillingSkill(Skill)` subclass
- WHEN `skill.register(mcp_instance)` is called
- THEN the skill's operations are registered as MCP tools on the instance
- AND tool names follow the pattern `skill_<operation_name>`

### Requirement: Composable Skill Operations

Each skill operation MUST compose atomic protocol calls (sketch → extrude → fillet) into a single higher-level operation.

#### Scenario: Drilling skill creates hole pattern

- GIVEN a `DrillingSkill` with an active part document
- WHEN `crear_patron_taladros(center_x, center_y, radius, count, hole_diameter, depth)` is called
- THEN it MUST:
  1. Create a sketch on the target face via `provider.sketch_ops`
  2. Draw `count` circles at calculated positions via `provider.sketch_ops.sketch_circle()`
  3. Extrude-cut each circle via `provider.feature_ops.extrude(operation="cut")`
  4. Return `{"success": True, "holes_created": count}`
- AND the skill MUST work with ANY `CADProvider` implementation

#### Scenario: Skill error rolls back gracefully

- GIVEN a `DrillingSkill` operation in progress
- WHEN step 3 (extrude-cut) fails on hole #4 of 8
- THEN the skill MUST return `{"success": False, "error": "...", "holes_created": 3}`
- AND partial results MUST be reported (not all-or-nothing)

### Requirement: Skills Are Provider-Agnostic

Skills MUST NOT import from `mcp_cad.inventor.*` or `mcp_cad.providers.*`. They interact with the backend exclusively through the `CADProvider` protocol.

#### Scenario: Skill imports only protocol

- GIVEN any file in `mcp_cad/skills/`
- WHEN inspected for imports
- THEN it MUST NOT import from `mcp_cad.inventor.*` or `mcp_cad.providers.*`
- AND it MUST import ONLY from `mcp_cad.core.protocol`, `mcp_cad.errors`, and `mcp_cad.skills`

#### Scenario: Skill works with mock provider

- GIVEN a `CADProvider` mock in tests
- WHEN a skill operation is called
- THEN the mock's methods are called in the expected sequence
- AND the test can verify the composition order without a real Inventor instance

### Requirement: At Least One Demonstrated Skill

The system SHALL include at least one complete skill that demonstrates chaining: sketch creation → extrude → fillet in a single operation.

#### Scenario: Bracket skill demonstrates full chain

- GIVEN a `BracketSkill` subclass
- WHEN `crear_soporte(width, height, thickness, hole_radius)` is called
- THEN it MUST:
  1. Create a new part document via `provider.document_ops`
  2. Create a sketch on XY plane
  3. Draw a rectangle of `width x height`
  4. Extrude to `thickness`
  5. Create a second sketch on the front face
  6. Draw a circle of `hole_radius`
  7. Extrude-cut the hole
  8. Apply fillet to outer edges
  9. Return `{"success": True, "feature_count": 4}`

### Requirement: Skills Registration in server.py

The system SHALL provide a `register_skills(mcp_instance: FastMCP, provider: CADProvider)` function that registers all available skills.

#### Scenario: Skills are registered after tools

- GIVEN `server.py` `main()` function
- WHEN the server initializes
- THEN `register_tools(mcp_instance, provider)` is called first
- AND `register_skills(mcp_instance, provider)` is called second
- AND skill tool names do not conflict with atomic tool names

## Non-Goals

- Building a skill DSL or configuration language — skills are plain Python classes
- Implementing undo/rollback for partial skill failures — partial results are reported
- Creating skills for every possible operation — only 1-2 example skills in this change
- Supporting skill versioning or migration — not needed for initial implementation
