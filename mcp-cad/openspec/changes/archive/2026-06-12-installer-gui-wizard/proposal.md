# Proposal: installer-gui-wizard

**Change**: installer-gui-wizard  
**Date**: 2026-06-10  
**Status**: Proposed (after explore)  
**Artifact store**: hybrid (this file in openspec/changes/installer-gui-wizard/; state + explore in engram sdd/installer-gui-wizard/*)  
**Delivery strategy**: ask-on-risk (see tasks phase for workload forecast and ~400 line budget / chained PR decision)  
**Related**: engram #257 (task), #258 (session), sdd-init/mcp-cad #72, skill-registry #74; replaces/complements tui-installer-completed work.

## Intent / Why
Non-technical Autodesk Inventor designers (the primary target users for mcp-cad) are not comfortable with terminals, console windows, Spectre.Console TUI navigation (j/k, arrows, Space/Enter), or even reading console output. The recent tui-improvements delivered a polished interactive TUI + strong non-interactive `--recommended` / `--all` / `--agents` CLI + McpCad-Install.bat for "download zip + double-click" flow. However, for true one-click "feels like a normal Windows app" experience, we need a classic Windows GUI wizard (welcome → agent selection with checkboxes/descriptions/CAD Skills/Backups toggle → per-agent progress → finish with explicit next steps).

The GUI must become the **primary path for end users** (double-click exe or .bat with no args from Explorer), while the existing TUI remains the "advanced / power user / scripting" path.

## Scope

### In
- Add WinForms-based wizard inside the existing `src/McpCad.Installer/` .NET 8 project (one self-contained portable exe).
- Wizard pages/screens:
  - Welcome / intro (mcp-cad branding, simple explanation for CAD users).
  - Select agents: checkboxes for OpenCode, Claude, Pi, VS Code, Cursor, Grok + "CAD Skills" (special item that deploys to all) + "Backups" toggle (quirúrgico defaults on, matches current TUI).
  - Defaults to the recommended set (Claude, Cursor, Grok, OpenCode, CAD Skills) for one-click.
  - Progress screen: status / spinner / message per agent as registration + skills copy runs (reuse existing logic).
  - Finish screen: success/fail table or list + clear instructions ("Close & reopen your AI client(s). Keep Inventor running.").
- Launch decision: GUI by default on no command-line args (typical double-click). Preserve exact CLI flag behavior and TUI when `--tui`, flags present, or console-attached advanced use.
- 100% reuse of existing backend: `McpAgents.All(state)`, agent `Run` delegates, `Register*`, `TryInstallSkills`/`InstallSkillsToAllAgents`, `Backup*` (quirúrgico), `FindServerPath`/`GetResolvedServerPath`, `ConfigManager`, `State` (BackupsEnabled etc.). No duplication of registration/skills/backup/discovery code.
- Update packaging: `scripts/publish-portable.ps1` (if needed for WinForms in single-file), `McpCad-Install.bat` (change default launch to no-arg GUI; support `--tui` for classic), README.md, docs/tools-reference.md (promote GUI as primary for non-tech, document TUI as advanced).
- Keep portable self-contained win-x64 publish working (net8.0-windows + UseWindowsForms acceptable since Windows + Inventor target).
- State persistence compat (use same `scripts/tui/state.json` or robust fallback).
- Full backward compat for all existing flags, .bat users, scripts, portable zips.

### Out (non-goals)
- No changes to McpCad.Server, Core, Inventor, Tools, or any MCP protocol/tools.
- No new skills or agent support (reuse the 7 items already defined).
- No Linux / cross-platform GUI (WinForms Windows-only is explicit match for target users).
- No replacement or removal of Spectre TUI code (it stays fully functional).
- No new dependencies beyond framework (WinForms is inbox for net8.0-windows).
- No automated unit tests for the installer GUI (installer is end-user tool; verification is manual portable package test + review of reuse).
- No changes to existing success messages / next-steps text (reuse/enhance where already good in non-int path).

## Approach
1. **Early mode selection in `Program.Main`** (before any Spectre or heavy console work): inspect `args`, console attachment/redirect, and (optionally) a new `--tui` flag. Route to:
   - CLI non-interactive paths (unchanged, for --recommended etc. and scripting).
   - Classic TUI (current Spectre loop, perhaps triggered by `--tui` or console presence).
   - New GUI wizard path (default for 0 args).
2. **GUI implementation**: Add WinForms forms or a simple wizard controller (e.g. `WizardForm.cs` or `Gui/` folder). Use `CheckBox` list for agents (pre-check recommended + respect auto-detect + State.Backups), `Button` for Continue/Back, `ProgressBar` + `Label` per row or log for progress, final `DataGridView` or list + "Finish" button that closes + reminds. Use `[STAThread]`, `Application.Run`.
3. **Console hiding for GUI default**: P/Invoke `kernel32.dll` `GetConsoleWindow` + `ShowWindow` (SW_HIDE) when entering pure GUI path. TUI/CLI paths keep/show console.
4. **Reuse layer**: Minor extraction if helpful (e.g. a `RunInstall(IEnumerable<McpAgent> selected, State state, string serverPath)` helper used by both TUI `InstallSelected` / non-int and the GUI progress handler). Or simply have GUI code do the same iteration + `agent.Run?.Invoke(...)` + update UI. All side-effects (backups, skills copy, config writes, state save) remain in the existing statics.
5. **Project / build**: Update `McpCad.Installer.csproj` to `net8.0-windows`, add `<UseWindowsForms>true</UseWindowsForms>`. Single-file self-contained publish continues to work (WinForms assemblies included).
6. **Launcher / packaging / docs updates** (small, targeted):
   - `.bat`: launch `"%EXE%"` (no args) for new GUI default; document or support `"%EXE%" --tui` for classic TUI.
   - `publish-portable.ps1`: no or trivial change (already publishes the exe).
   - README + docs: update quickstart to lead with GUI wizard experience; note "For power users / automation: use --tui or the CLI flags".
7. **Hybrid SDD artifacts**: proposal/design/specs/tasks in openspec/changes/installer-gui-wizard/ + engram state under sdd/installer-gui-wizard/*. Follow conventions (English technical, capture_prompt=false for mem artifacts).

**Key patterns reused**: Exact same as tui-installer delivery (centralized McpAgent + delegates, quirúrgico backups, portable discovery, recommended defaults, State for prefs).

**Open questions for design** (to be resolved in design phase):
- Exact console detection heuristic for "double-click from Explorer" (args.Length==0 && !Console.IsInputRedirected && GetConsoleWindow() != IntPtr.Zero or similar).
- Whether to keep "scripts/tui/state.json" path or move installer prefs (compat vs cleanliness).
- Progress UI details (per-agent ListView with status icons vs simple sequential labels).
- Support "Back" button between wizard pages (user decision: YES - include navigation).
- Error handling / partial success in GUI (mirror current results table).

## Risks & Mitigations
- **csproj target change (net8.0 → net8.0-windows)**: Acceptable (project already Windows/Inventor-only). Mitigate by verifying full publish + run on clean Windows box in verify phase. Risk low.
- **Console window flash or visibility on GUI double-click**: Use P/Invoke hide. If flash remains, consider WinExe + AllocConsole only for --flags/TUI paths (higher complexity). Mitigate in design/apply.
- **Portable single-file + WinForms payload / startup**: .NET 8 supports it; size increase small. Verify in publish + end-to-end test.
- **State path in portable (current "scripts/tui/state.json" rarely exists)**: GUI inherits same behavior (clean start). Can improve robustness without breaking.
- **Breaking existing .bat / flag users or scripts**: None, because CLI paths untouched; .bat change is additive (default now GUI, --tui for old behavior). Docs updated.
- **Workload / review budget**: GUI layer new code + glue + 4 small updates. Estimate 300-600 LOC changed. Per guard: honor tasks.md forecast; default ask-on-risk (may recommend chained PRs or size:exception for full apply).
- **No live Inventor needed for installer**: Good (unlike server tools).
- **Duplication risk**: Strict review in apply/verify that GUI only orchestrates existing `McpAgents` / `Run` / backups.

## Success Criteria
- Double-click of published portable `McpCad.Installer.exe` or `McpCad-Install.bat` (no args) launches a clean WinForms wizard (no console window or hidden immediately).
- Default selection = recommended set; user can toggle CAD Skills + Backups; "Continue" runs the exact same registration + skills deployment logic as before.
- Progress shows per-agent feedback; finish screen has the required next-steps text.
- `McpCad.Installer.exe --recommended` (and other flags) continue to work exactly as before (console output, no GUI).
- `McpCad.Installer.exe --tui` (or equivalent) launches the full existing Spectre TUI.
- All quirúrgico backups, skills copy to 6 locations, Grok Tomlyn special case, portable server discovery, State prefs continue to function identically.
- Updated docs clearly direct non-technical users to the GUI flow.
- Portable package still builds and is self-contained.
- Existing TUI users / advanced flows unaffected (no regressions in TUI screens, key handling, success table, non-int paths).
- Verified manually on Windows (portable zip extract + double-click + at least one agent registration + skills present + backup created).

**Out of scope for success**: New unit tests, cross-platform, new agents, changes to MCP server itself.

## References
- Task: engram #257
- Session: engram #258
- Current implementation: src/McpCad.Installer/* (Program.cs, McpAgent.cs, ...), scripts/publish-portable.ps1, McpCad-Install.bat, README.md
- Prior SDD: openspec/changes/tui-installer* + archive/2026-06-07-tui-installer-completed/
- Explore artifact: engram sdd/installer-gui-wizard/explore
- Init: engram sdd-init/mcp-cad + skill-registry

Ready for sdd-spec (formal GIVEN/WHEN/THEN from this + explore) and sdd-design (file changes, integration points, P/Invoke details, tradeoffs).