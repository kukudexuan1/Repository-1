# TUI Pluggable Registry Specification

## Purpose

Defines the decorator-based self-registration system for menu items. New agents are added by creating a single file with a `@register_item` decorator — no core TUI code changes required.

## Requirements

### Requirement: MenuItem Base Class

The system MUST define an abstract base class `MenuItem` in `scripts/tui/items/base.py` with the following abstract members:

| Member | Type | Description |
|--------|------|-------------|
| `name` | `str` | Display title |
| `description` | `str` | Short explanation shown in menu |
| `category` | `str` | One of: `"agent"`, `"system"`, `"future"` |
| `is_enabled` | `bool` | Whether the item is selectable (default `True`) |
| `run()` | `Callable` | Abstract method executed on Enter |

#### Scenario: Concrete item implements all abstract members

- GIVEN a class inherits from `MenuItem`
- WHEN instantiated
- THEN it MUST implement `name`, `description`, `category`, `is_enabled`, and `run()`
- AND missing any abstract member MUST raise `TypeError` at class definition time

#### Scenario: Category validation

- GIVEN a concrete `MenuItem` subclass
- WHEN `category` is set to a value not in `["agent", "system", "future"]`
- THEN the system MUST raise `ValueError`

### Requirement: @register_item Decorator

The system MUST provide a `@register_item(name, description, category)` decorator in `scripts/tui/registry.py` that auto-registers decorated classes into a global registry.

#### Scenario: Decorator registers a class

- GIVEN a class decorated with `@register_item("OpenCode", "Register OpenCode agent", "agent")`
- WHEN the module is imported
- THEN an instance of the class MUST be appended to the global registry

#### Scenario: Decorator preserves class identity

- GIVEN a class decorated with `@register_item`
- WHEN the class is referenced directly
- THEN it MUST remain the original class (decorator MUST NOT replace it)

### Requirement: Registry Query Interface

The system MUST provide the following functions in `scripts/tui/registry.py`:

| Function | Returns | Description |
|----------|---------|-------------|
| `get_all()` | `list[MenuItem]` | All registered items |
| `get_by_category(category: str)` | `list[MenuItem]` | Items filtered by category |

#### Scenario: Get all registered items

- GIVEN three items are registered (2 agent, 1 system)
- WHEN `get_all()` is called
- THEN it MUST return a list of 3 `MenuItem` instances

#### Scenario: Filter by category

- GIVEN items exist in categories "agent" and "system"
- WHEN `get_by_category("agent")` is called
- THEN it MUST return only items where `category == "agent"`

#### Scenario: Filter by unknown category

- GIVEN no items exist in category "future"
- WHEN `get_by_category("future")` is called
- THEN it MUST return an empty list

### Requirement: Import-Time Registration

The system MUST auto-discover and register all items in `scripts/tui/items/*.py` when the registry module is initialized. Each item module MUST be imported to trigger its `@register_item` decorator.

#### Scenario: All item modules are loaded

- GIVEN `items/opencode.py`, `items/claude.py`, and `items/pi.py` exist
- WHEN the registry initializes
- THEN all three modules MUST be imported
- AND `get_all()` MUST return 3 items

#### Scenario: New item auto-registered

- GIVEN a developer creates `items/new_agent.py` with `@register_item`
- WHEN the TUI starts
- THEN the new item MUST appear in the menu without core code changes
