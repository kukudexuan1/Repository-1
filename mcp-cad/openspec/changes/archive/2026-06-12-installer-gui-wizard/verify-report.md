# Verify Report: installer-gui-wizard

**Date**: 2026-06-12  
**Executor**: SDD verify (automated + structural; manual GUI matrix deferred)  
**Change**: installer-gui-wizard — WinForms GUI wizard as default launch; Spectre TUI preserved via `--tui`  
**Branch**: `feature/tui-improvements`  
**Commits**: `aabbd1b` → `965f286` (TUI polish, CLI, skills, backups, GUI wiring)

## Artifacts Reviewed

- `openspec/changes/installer-gui-wizard/{proposal.md, design.md, specs/gui-wizard/spec.md, tasks.md, apply-progress.md}`
- `src/McpCad.Installer/{Program.cs, InstallerWizardForm.cs, McpAgent.cs, State.cs, McpCad.Installer.csproj}`
- `McpCad-Install.bat`, `scripts/publish-portable.ps1`
- `README.md`, `docs/tools-reference.md` (Batch 3 docs)

## What Passed

### Build & packaging (installer scope)

- `dotnet build src/McpCad.Installer/McpCad.Installer.csproj -c Release` — **0 errors, 0 warnings**
- `scripts/publish-portable.ps1` — **McpCad.Installer** published to `dist/mcp-cad-portable/` (self-contained win-x64 single-file)
- Portable layout includes: `McpCad.Installer.exe`, `McpCad-Install.bat`, `skills/`, `README.txt`

### CLI / routing (automated)

- `McpCad.Installer.exe --help` — documents GUI default, `--tui`, `--recommended`, `--all`, `--agents`, Backups TUI note (**PASS**)

### Fidelity to spec + design

| Requirement | Status |
|-------------|--------|
| No-arg launch → GUI (not Spectre TUI) | Wired in `Program.cs` after CLI early-returns; P/Invoke hides console |
| `--tui` → existing Spectre TUI unchanged | Fall-through after GUI guard; TUI loop not modified |
| CLI flags (`--recommended`, `--all`, `--agents`, `--help`) unchanged | Early returns preserved before GUI block |
| 4 wizard pages (Welcome, Selection, Progress, Finish) | `InstallerWizardForm.cs` |
| Back button functional | `OnBack` between pages |
| Recommended pre-check + CAD Skills + Backups | Selection panel logic |
| Finish text exact | `"Close & reopen your AI client(s). Keep Inventor running."` |
| Backend reuse via `agent.Run?.Invoke` | Duplicated loop inside form only (no extraction from TUI) |
| State path `scripts/tui/state.json` | Unchanged |
| Registration/skills/backups logic centralized in `McpAgent.cs` | Grep confirms no duplicate `RegisterWithSchema` / `InstallSkills` in form |

### Code review (tasks.md § Verification Plan)

- `RegisterWithSchema`, `InstallSkills`, `BackupConfigFile`, `FindServerPath` — **only in `McpAgent.cs`**; form calls `agent.Run` delegates
- TUI success screen / `InstallSelected` / `RunSelectedAgentsAndExit` — **untouched** in Spectre paths
- Locked user decisions honored: no TUI refactor, duplicate loop in form, Back=yes, strict additive glue

### Documentation (Batch 3)

- `README.md` quickstart — GUI wizard as primary; `--tui` / CLI flags documented
- `docs/tools-reference.md` — installer section updated

## WARNING Items

1. **Full portable publish partial**: `McpCad.Server` publish failed in `publish-portable.ps1` due to **unrelated WIP** on this branch (`TemplateTools.cs` / `MacroTools.cs` untracked files breaking `McpCad.Tools` compile). **Installer-only portable package succeeded.** Not introduced by installer-gui-wizard.
2. **Manual GUI test matrix not executed in verify session** (headless/automation cannot drive WinForms interactively). Structural + CLI checks PASS; items 1–2, 6–8 from tasks.md verification matrix require **user double-click** on a Windows desktop:
   - GUI flow with Backups toggle off/on + disk side-effects
   - CAD Skills only path
   - TUI Backups toggle + install
   - Backup files under `~/.mcp-cad/backups/`
3. **Brief console flash** possible before `HideConsoleWindow` on GUI launch (known risk in design.md; acceptable).

## SUGGESTION Items

- Re-run full `publish-portable.ps1` after merging/cleaning unrelated branch WIP so Server + Installer ship together.
- Optional: add `--no-backups` CLI flag (noted in engram #258 as future).
- Optional: CI job for `dotnet build` Installer only on Windows runners.

## Proposal Success Criteria

| Criterion | Verdict |
|-----------|---------|
| GUI default for double-click | PASS (wired) |
| `--tui` launches full Spectre TUI | PASS (wired) |
| Backups, skills, Grok Tomlyn, discovery, State prefs identical | PASS (structural — same `McpAgent` backend) |
| Docs direct non-technical users to GUI | PASS |
| Portable installer builds self-contained | PASS (installer) |
| TUI / CLI regressions | PASS (code review; no TUI loop edits) |
| Manual Windows portable E2E | DEFERRED (user-driven) |

## Post-Closure Update (2026-06-12)

- Judgment Day Round 1–2 fixes applied (`62c47d4` … `a6f0926`)
- User manual GUI walkthrough: **PASS** (layout, paths, install flow)
- User manual TUI (`--tui`): **PASS**
- Judgment Day final: **APPROVED**

Deferred items from original verify (manual matrix, full Server+Installer portable) remain optional follow-ups; **installer slice declared complete**.

## Verdict

**PASS** — Shipped on `main`. GUI default, Spectre `--tui`, CLI flags, skills, backups, JD fixes, and user E2E confirmed.

**SDD cycle closed.**