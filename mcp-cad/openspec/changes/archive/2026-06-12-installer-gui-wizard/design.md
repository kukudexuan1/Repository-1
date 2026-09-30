# Design: installer-gui-wizard

**Change**: installer-gui-wizard  
**Based on**: proposal.md, specs/gui-wizard/spec.md, explore report (engram), current codebase analysis (Program.cs, McpAgent.cs full, csproj, publish-portable.ps1, .bat, README, archived tui specs).  
**Date**: 2026-06-10  
**Artifact store**: hybrid

## Architecture Overview
The installer remains a single self-contained .NET 8 win-x64 executable. The existing dual-path architecture (non-interactive CLI vs interactive TUI) is extended with a third path: GUI wizard. Mode selection happens **as early as possible in `Program.Main`** (before `_state = State.Load...`, before any Spectre or Console.Clear/Write, before McpAgents.All if possible for pure GUI).

Shared backend (McpAgents, ConfigManager, State, backup/skills helpers) is **untouched in behavior** — GUI is a pure consumer/orchestrator of the existing delegates and static methods.

High-level flow after change:
```
Main(string[] args)
  resolve early serverPath? (or lazy)
  if (IsCliNonInteractive(args)) { set selected per flags; RunSelected...; return; }
  if (ForceTui(args) || HasConsoleIntent(args)) { old TUI code (unchanged); return; }
  // default / GUI path
  HideConsoleIfPossible(); // P/Invoke
  var state = State.Load(...);
  var agents = McpAgents.All(state);
  // auto-detect can still run (cheap)
  LaunchGuiWizard(agents, state, serverPath); // blocks until finish/close
```

`LaunchGuiWizard` (new) creates the WinForms wizard, wires events to:
- On selection Continue: collect checked agents → run the install sequence by iterating and calling `agent.Run?.Invoke(state, agent)` (or a thin shared helper) while updating form controls (cross-thread via BeginInvoke or BackgroundWorker/Task + Control.Invoke).
- Reuse `McpAgents.GetResolvedServerPath()` for display / pass-through.
- Backups toggle directly mutates the State instance (or a viewmodel that syncs) so that when Run is called the `state` passed carries the current enabled flag (matching how TUI does `_state.BackupsEnabled = ...` before Run).

No new registration or copy code.

## File / Project Changes (Concrete)

### 1. src/McpCad.Installer/McpCad.Installer.csproj (small, critical)
- Change `<TargetFramework>net8.0</TargetFramework>` → `net8.0-windows`
- Add `<UseWindowsForms>true</UseWindowsForms>`
- (Optional but recommended) `<ApplicationManifest>` or leave default for exe.
- No new PackageReferences (WinForms is framework).
- Publish behavior unchanged (single-file self-contained will embed required assemblies).

Impact: ~3 lines changed. Forces Windows build (already reality).

### 2. src/McpCad.Installer/Program.cs (moderate glue + preservation)
- Keep all existing using, consts, LogoLines, fields, AutoDetectAgents, InstallSelected, ShowSuccessScreen, RunSelectedAgentsAndExit, RunAgent, RenderLogo, key handling, etc. **100% intact** for TUI/CLI paths.
- Add at top: `using System.Runtime.InteropServices;` (for P/Invoke) + `using System.Windows.Forms;` (for the GUI path).
- Early in Main (after var serverPath = ... but before TUI objects):
  ```csharp
  if (args.Any(a => /* CLI flags */)) { ... existing non-int; return; }
  if (args.Any(a => a.Equals("--tui", StringComparison.OrdinalIgnoreCase)) ||
      /* console intent heuristic, e.g. Console.IsInputRedirected or parent process check */ )
  {
      // fall through to existing TUI code (or call a RunTui() extracted)
      ...
  }
  // GUI default path
  HideConsoleWindow();
  var state = State.Load(StatePath);
  var agents = McpAgents.All(state);
  AutoDetectAgents(agents); // still useful for GUI pre-checks
  ApplicationConfiguration.Initialize(); // .NET 8 WinForms best practice
  Application.Run(new InstallerWizardForm(agents, state, serverPath));
  ```
- Add the P/Invoke helpers (private static):
  ```csharp
  [DllImport("kernel32.dll")] private static extern IntPtr GetConsoleWindow();
  [DllImport("user32.dll")] private static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  private const int SW_HIDE = 0;
  private static void HideConsoleWindow() { var h = GetConsoleWindow(); if (h != IntPtr.Zero) ShowWindow(h, SW_HIDE); }
  ```
- Extract if clean: a small `void RunInstallForSelection(McpAgent[] selected, State state, string serverPath)` used by both old InstallSelected and the GUI progress handler (optional; keeps diff small).
- Remove or conditional the old `while (inSelection)` TUI block when in GUI path (structure with early returns).

New code surface: ~80-150 LOC (mode logic + P/Invoke + form launch). TUI code untouched.

### 3. New: src/McpCad.Installer/InstallerWizardForm.cs (or Gui/InstallerWizardForm.cs) — the main new artifact (~250-400 LOC)
- `public partial class InstallerWizardForm : Form { ... }`
- Constructor takes `McpAgent[] agents, State state, string serverPath` (or resolves inside).
- Use a `TabControl` or simple panel swap / UserControl per "page" for wizard feel (or single form with visible panels + Next/Back that hide/show).
- Pages (panels or separate controls):
  - WelcomePanel: logo (reuse text or PictureBox + embed simple resource or draw), label text, Next button.
  - SelectionPanel: `CheckedListBox` or `FlowLayoutPanel` of `CheckBox` + `Label` (description) for the 8 items. "CAD Skills" and "Backups" special (Backups as CheckBox that syncs state.BackupsEnabled and mutates the McpAgent description if shown). Pre-check logic for recommended + auto-detect.
  - ProgressPanel: `ListView` (Agent, Status, Details) or `DataGridView`; `Button` disabled during run. On start: disable nav, for each selected: update row, invoke Run (on threadpool or Task, marshal UI updates with `this.Invoke`), collect results.
  - FinishPanel: summary label, `ListView` or `DataGridView` of results (reuse the tuple style from current success), the required next-steps paragraph, Close button.
- Event wiring: Next/Back/Continue/Finish/Exit click handlers.
- On form load/Shown: set title "mcp-cad Installer", icon if possible (reuse or none), center, etc.
- Error handling mirrors current (per-agent catch, show in details).
- On finish Close: `Application.Exit()` or `this.Close()`.
- Make it resizable/minimal but usable (no heavy layout needed; simple Anchor or TableLayoutPanel).
- STAThread will be on the GUI entry (in Program or the form's Main if we keep single entry).

This is the bulk of new code. Must be self-contained in the file(s).

### 4. src/McpCad.Installer/McpAgent.cs (zero or near-zero change)
- Ideally **no edits** — all public surface (McpAgent, McpAgents.All, GetResolvedServerPath, the Run delegates, InstallSkillsToAllAgents, internal backup helpers via state) already sufficient.
- If a tiny shared runner helper is extracted for cleanliness, it can live here (or in a new thin InstallOrchestrator.cs). Prefer zero change for risk.

### 5. src/McpCad.Installer/State.cs (zero change)
- Already carries BackupsEnabled + Preferences. GUI will load/save the same way (or pass the instance). If path robustness desired, can enhance Load, but keep minimal.

### 6. scripts/publish-portable.ps1 (zero or 1-line comment)
- No functional change required. The publish already produces the single-file exe; WinForms assemblies will be included automatically for the windows TFM. Add a comment noting "GUI wizard (WinForms) added — net8.0-windows + UseWindowsForms".

### 7. McpCad-Install.bat (small, user-facing)
- Change the launch line from `"%EXE%" --recommended` to `"%EXE%"` (GUI default, recommended pre-selected inside wizard).
- Optionally support forwarding args: `"%EXE%" %*` so users can still do `McpCad-Install.bat --tui` or `... --agents ...`.
- Update the echo text slightly if needed ("Launching GUI installer wizard..." or keep generic).
- Keep the final pause + reminder messages (they are still useful if .bat used with flags).

### 8. README.md + docs/tools-reference.md (small doc updates)
- Quickstart: lead with "1. ... 4. **Double-click `McpCad-Install.bat`** (opens the GUI wizard — recommended for most users)."
- Describe the pages briefly or note "The wizard lets you choose agents with checkboxes (defaults to Claude/Cursor/Grok/OpenCode + CAD Skills), toggle backups, see progress, and get clear finish instructions."
- Add or update a "For advanced users / automation / terminal" subsection: "Run `McpCad.Installer.exe --tui` (or pass --tui to the .bat) for the classic interactive console TUI. All `--recommended`, `--all`, `--agents`, `--help` flags continue to work for scripts and power users."
- Keep competitive table and other content.
- In architecture or "How it works" if installer mentioned, note "TUI or GUI installer (Spectre.Console + WinForms)".

### 9. New / updated engram + openspec (orchestrator artifacts)
- openspec/changes/installer-gui-wizard/{proposal.md (done), design.md (this), specs/gui-wizard/spec.md (done), tasks.md, apply-progress.md, verify-report.md}
- engram: sdd/installer-gui-wizard/{state, explore, proposal, spec, design, tasks, ...} via mem_ (prompt proxy or proper mem_save in full runs).
- .grok/skill-registry.md no change (no new project skill).

## Trade-offs & Decisions

**WinForms vs WPF**: WinForms chosen (simpler, smaller payload for portable, sufficient for checkbox list + progress + finish, zero extra NuGet, matches "classic installer wizard" request). WPF would be overkill and increase size.

**OutputType / console strategy**: Keep OutputType=Exe (current). Use P/Invoke hide only for GUI path. Alternative (WinExe + AllocConsole on demand for TUI/CLI) considered but rejected for higher risk to existing console output paths and .bat messages. Hide is low-risk and common.

**Mode detection heuristic**: args.Length==0 + !Console.IsInputRedirected + (optional GetConsoleWindow check or parent process name). Can be refined in apply; documented in code. --tui always forces TUI for explicit power-user request.

**Shared runner extraction**: NO — do not extract.  
User decision (locked before apply): "la tui ya me agrada no se debería tocar nada".  
Duplicate the ~10-line execution loop inside InstallerWizardForm. This guarantees zero changes to any existing TUI code paths (InstallSelected, etc.).

**State path**: Leave exactly as-is ("scripts/tui/state.json").  
User decision before apply: do not change the path. GUI must use the identical Load/Save as current TUI for full compatibility.

**Back button in wizard**: YES — implement functional Back navigation between pages.  
User decision locked before apply.

**Error / partial success**: Mirror current (per-agent results, continue on error). GUI shows red status per row.

**Resources / icon / branding**: Minimal — text + electric orange where easy in WinForms (no embedded binary changes unless trivial). Reuse logo text lines if wanted.

**Testing strategy**: No new xUnit (per init: installer not unit-tested today). Verification = manual portable extract + double-click flow + flag regression + TUI launch + one full registration + skills/backup check on disk. Document steps in verify-report.

## Estimated Changed Lines & Workload
- csproj: ~3
- Program.cs: ~100-150 (mostly new early-return paths + P/Invoke; TUI block preserved)
- New form: ~300-450 (controls, 4 pages, event logic, reuse calls)
- .bat: ~5-8
- README + docs: ~15-25
- **Total new/changed source ~450-650 LOC** (plus the 4-5 small doc/spec files which are SDD artifacts, not "code" for budget).
- Per review guard: will be detailed in tasks.md with phases/batches. Likely "ask-on-risk" or "chained PRs recommended" (e.g. Phase 1: csproj + Program skeleton + hide; Phase 2: full form + reuse calls; Phase 3: .bat + docs). 400-line budget honored by slicing or explicit exception in tasks.

## Open Decisions / Risks (to be confirmed in tasks/apply)
- Exact heuristic for "GUI intent" (test on real Explorer double-click vs cmd / pwsh / shortcut).
- Whether to make the form partial + .Designer.cs (VS style) or pure code (recommended for git-friendly, no designer needed).
- Threading for progress (simple Task.Run + Invoke is fine; no complex BackgroundWorker required).
- If single-file publish of net8.0-windows + WinForms has any gotcha on clean machines (verify will catch).
- State.json path in GUI (current portable always fresh; acceptable).

## Diagrams (text)
```
User double-click (no args)
  -> Main
     -> not CLI flag
     -> not --tui / console intent
     -> HideConsole()
     -> new InstallerWizardForm( McpAgents.All(state), state, GetResolved... )
        -> pages (selection pre-checks recommended + auto-detect)
        -> on Continue: foreach selected { update UI; results += agent.Run(state, agent) /* exact same */ ; }
        -> finish page with next steps text
```

All side-effects (config edits, skills copies, backups under ~/.mcp-cad, state save) identical to pre-change.

## Verification Hooks
- sdd-verify will run the manual steps + confirm no duplication via code review + grep for "Register|InstallSkills|Backup" only in McpAgent.cs (except calls from new GUI).
- Update apply-progress.md and verify-report.md during later phases.

This design satisfies the "reuse every piece", "preserve 100% compatibility", "GUI default for non-tech", "keep TUI advanced" requirements from the proposal and spec. Ready for tasks breakdown.