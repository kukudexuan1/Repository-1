# Apply Progress: installer-gui-wizard

**Change**: installer-gui-wizard  
**Status**: **COMPLETE** — all batches done; verified; archived 2026-06-12  
**Branch**: `feature/tui-improvements`

## Batches Completed

### Batch 1 / Phase 1 (csproj + routing + .bat)
- `net8.0-windows` + `UseWindowsForms`
- P/Invoke `HideConsoleWindow`
- GUI default routing in `Program.cs` (after CLI blocks)
- `McpCad-Install.bat` → `"%EXE%" %*`
- Commit: `965f286` (combined with Batch 2 wiring in practice)

### Batch 2 / Phase 2 (InstallerWizardForm + glue)
- `InstallerWizardForm.cs` — 4 pages, Back, recommended pre-check, CAD Skills + Backups, duplicated `agent.Run` loop, threading, electric orange
- `Program.cs` — `Application.Run(new InstallerWizardForm(...))` on no-arg path
- TUI/CLI paths untouched

### Batch 3 / Phase 3 (polish + verify + archive)
- `README.md` + `docs/tools-reference.md` — GUI-first quickstart, `--tui` for advanced
- `verify-report.md` — PASS WITH WARNINGS
- `archive-report.md` — archived to `openspec/changes/archive/2026-06-12-installer-gui-wizard/`

## TUI prerequisite (same branch)

Completed on `feature/tui-improvements` before GUI wiring:
- `aabbd1b` — TUI polish (Continue, success screen, autodetect)
- `b7e8a4f` — CLI flags + `McpCad-Install.bat` + portable script
- `49d3f3e` — CAD Skills deployment
- `18fff21` — quirúrgico backups + TUI Backups toggle

## Verification Evidence

- Installer Release build: 0 errors
- Portable installer publish: `dist/mcp-cad-portable/McpCad.Installer.exe` OK
- `--help` output documents GUI + `--tui` + CLI flags
- Server publish blocked by unrelated branch WIP (documented in verify-report)

## Deviations

None from spec/design. Manual WinForms E2E deferred to user (headless verify environment).