# Archive Report: tui-installer (superseded)

**Archived**: 2026-06-12  
**Original location**: `openspec/changes/tui-installer/`  
**Archive location**: `openspec/changes/archive/2026-06-12-tui-installer-superseded/`  
**Status**: **SUPERSEDED** — not delivered as specified

## Executive Summary

This change proposed a Python `prompt_toolkit` TUI under `scripts/tui/`. Delivery moved to the **C# `McpCad.Installer`** project (Spectre.Console TUI + WinForms GUI wizard) on branch `feature/tui-improvements`, merged to `main` on 2026-06-12.

Only foundation work (Phases 1–2, tasks T1–T7) was partially applied in a prior session; no Python menu items, tests, or entry point shipped in the repo. The surviving artifact is `scripts/tui/state.json` (shared path name with the C# installer).

## Superseded By

| Delivered instead | Location |
|-------------------|----------|
| Spectre TUI (`--tui`) | `src/McpCad.Installer/Program.cs` |
| GUI wizard (default) | `src/McpCad.Installer/InstallerWizardForm.cs` |
| Combined SDD archive | `openspec/changes/archive/2026-06-12-installer-gui-wizard/` |

## Verdict

**CLOSED — SUPERSEDED** — No further work on the Python TUI track.