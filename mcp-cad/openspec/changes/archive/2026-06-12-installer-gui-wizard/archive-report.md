# Archive Report: installer-gui-wizard

**Archived**: 2026-06-12  
**Branch**: `feature/tui-improvements`  
**Original location**: `openspec/changes/installer-gui-wizard/`  
**Archive location**: `openspec/changes/archive/2026-06-12-installer-gui-wizard/`

## Executive Summary

Added a Windows Forms GUI wizard to `McpCad.Installer` as the **default** experience for download-and-double-click users, while preserving the existing Spectre.Console TUI (`--tui`) and all CLI flags (`--recommended`, `--all`, `--agents`, `--help`). Backend registration, CAD skills deployment, and quirúrgico backups remain centralized in `McpAgent.cs`; the wizard duplicates only the small per-agent execution loop inside `InstallerWizardForm.cs` per locked user decision.

**Verdict**: PASS WITH WARNINGS (see verify-report.md)

## Delivery

| Batch | Scope | Status |
|-------|-------|--------|
| 1 | `net8.0-windows`, P/Invoke, routing skeleton, `.bat` | Complete (`965f286`) |
| 2 | `InstallerWizardForm.cs` (4 pages, Back, reuse) | Complete |
| 3 | Docs, verify, archive | Complete (this archive) |

**Chained PRs**: Applied as sequential commits on `feature/tui-improvements` (TUI commits `aabbd1b`–`49d3f3e`, backups `18fff21`, GUI `965f286`).

## Key Files (production)

| File | Role |
|------|------|
| `src/McpCad.Installer/InstallerWizardForm.cs` | WinForms wizard UI |
| `src/McpCad.Installer/Program.cs` | Mode routing: CLI → GUI default → `--tui` TUI |
| `src/McpCad.Installer/McpCad.Installer.csproj` | `net8.0-windows` + WinForms |
| `McpCad-Install.bat` | Launches exe with `%*` (GUI default) |
| `README.md`, `docs/tools-reference.md` | User-facing GUI-first docs |

## Locked Decisions (honored)

- Do not modify Spectre TUI loop — **honored** (additive routing only)
- Duplicate install loop inside form — **honored**
- Back button — **implemented**
- State path `scripts/tui/state.json` — **unchanged**
- Strict TDD during apply batches — documented in apply-progress

## Post-Archive Completion (2026-06-12)

| Commit | Scope |
|--------|-------|
| `62c47d4` | Judgment Day Round 1 fixes (server guard, threading, validation, CLI exit codes) |
| `1ffb13d` | Bat exit-code propagation; GUI double-click guard |
| `e680159` | MCP path labels for all agents; initial padding |
| `a6f0926` | TableLayoutPanel layout — page controls no longer under nav bar |

**Judgment Day**: `JUDGMENT: APPROVED ✅` (installer slice)  
**Manual E2E**: User confirmed GUI + TUI functional on Windows (2026-06-12)  
**Merge**: `feature/tui-improvements` → `main` (closure commit)

## Follow-ups (out of scope — installer slice closed)

- Full portable publish when unrelated Server WIP no longer breaks `publish-portable.ps1`
- Optional: `--no-backups` CLI flag