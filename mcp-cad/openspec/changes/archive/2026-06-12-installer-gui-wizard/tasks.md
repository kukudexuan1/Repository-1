# Tasks: installer-gui-wizard

**Change**: installer-gui-wizard  
**Based on**: proposal.md, specs/gui-wizard/spec.md, design.md, explore (engram), current code.  
**Review Workload Guard**: ~400-600 LOC estimate for implementation (mostly new GUI form + small glue in Program + csproj/.bat/docs). **Default delivery: ask-on-risk**. Chained PRs recommended if full apply exceeds comfortable single-PR review size (orchestrator + reviewer decide at apply time). Strict TDD: **true** (user decision before apply: "Strict tdd = true, siempre en true". Overrides project init default for this change).  
**Artifact store**: hybrid.  
**Skill resolution for phases**: paths-injected (sdd-phase-common + sdd-orchestrator).  

## Overall Phases (for apply batches)
Apply can be done in 2-3 small batches if needed for review protection:
- Batch 1 (low risk, ~150 LOC): csproj + Program.cs skeleton (mode selection, P/Invoke, early exit to GUI stub) + .bat + basic docs.
- Batch 2 (core, ~350 LOC): full InstallerWizardForm.cs + reuse calls + progress/finish logic + spec compliance.
- Batch 3 (small): polish, full docs/README update, any shared runner extraction, final verify prep.

Each batch produces update to apply-progress.md.

## Task List (Reviewable, Ordered, Testable where possible)

### Phase 0: SDD Foundation (this change — mostly complete when tasks approved)
- [x] Guard + explore (mem searches for sdd-init #72, task #257, session #258; 4+ files + grep + list_dir on Installer, publish, .bat, archived specs; skills loaded; engram state created).
- [x] proposal.md (intent/scope/approach/risks/success; English).
- [x] specs/gui-wizard/spec.md (GIVEN/WHEN/THEN for launch, 4 pages, reuse, compat, constraints).
- [x] design.md (architecture, exact file deltas, tradeoffs, P/Invoke, est LOC, diagrams).
- [x] tasks.md (this file — with workload table, batching, verification).
- [x] Create openspec/changes/installer-gui-wizard/apply-progress.md skeleton (updated per batch).
- [x] Create / update engram sdd/installer-gui-wizard/state (current phase, decisions, delivery).

**Owner**: Orchestrator (this run).  
**Verification**: All prior artifacts present + consistent with spec.

### Phase 1: Project & Entry Point (csproj + Program.cs + .bat)
**Goal**: Make the project build a WinForms-capable exe; route no-arg launches to a stub GUI path (or direct form if Batch 2 combined); preserve every line of TUI/CLI behavior; update launcher default.

1.1 Update McpCad.Installer.csproj  
- Change TargetFramework to net8.0-windows.  
- Add `<UseWindowsForms>true</UseWindowsForms>`.  
- Verify `dotnet build -c Release` and `dotnet publish ... win-x64 --self-contained ...` still succeed (single-file).  
- **Deliverable**: csproj diff only. No behavior change yet.  
- **Test**: Build + publish succeeds; resulting exe runs (will show console until GUI wired).

1.2 Add P/Invoke helpers + early GUI routing skeleton in Program.cs  
- Add the two DllImport + SW_HIDE const + HideConsoleWindow() private static (place near top with other privates).  
- Restructure Main early returns: keep all existing if (args.Any --all / --recommended / --agents / --help) blocks exactly.  
- Add after the CLI blocks:  
  `if (args.Any(a => a.Equals("--tui", StringComparison.OrdinalIgnoreCase)) /* || other console heuristic */) { /* fall to existing TUI code */ }`  
- Else (GUI default): `HideConsoleWindow();` then load state/agents/AutoDetect (keep for future), then `ApplicationConfiguration.Initialize(); Application.Run(new InstallerWizardForm(...));` (the class can be stub for now — empty form or simple MessageBox to prove launch).  
- Keep the entire old interactive TUI `while (inSelection)` block and all helper methods (InstallSelected, ShowSuccessScreen, etc.) untouched.  
- Add comment: "// GUI wizard path added for installer-gui-wizard; TUI preserved for --tui / advanced".  
- **Deliverable**: Program.cs changes (new ~60-100 LOC, zero deletions from TUI paths).  
- **Test (manual)**: `McpCad.Installer.exe --recommended` still does non-int console exactly. `McpCad.Installer.exe --tui` (or without after temp stub) shows TUI or stub. Double-click style (no arg) eventually shows form (after 1.3 + form).

1.3 Update McpCad-Install.bat for new default  
- Change launch from `"%EXE%" --recommended` to `"%EXE%"` (or `"%EXE%" %*` to forward any args).  
- Update title/echo text minimally ("Launching mcp-cad installer wizard..." or keep similar).  
- Keep the final pause + "Remember: restart AI client + Inventor" block (still accurate and useful).  
- **Deliverable**: .bat diff (~5 lines).  
- **Test**: Double-click .bat from portable layout launches the (stub) GUI.

1.4 Minimal docs touch (README + docs/tools-reference.md) — can be in this batch or later  
- Update quickstart to mention GUI wizard as primary double-click experience.  
- Add note about --tui for classic TUI.  
- **Deliverable**: Small md diffs.  
- **Test**: Docs read naturally.

**Risk / workload for Phase 1**: Low. ~100-150 LOC + docs. Safe first PR or batch. Verifies build/publish/compat for flags before investing in form.

**Owner for apply**: sdd-apply sub-agent (or human+agent pair).

### Phase 2: Core GUI Wizard Implementation (InstallerWizardForm.cs + reuse)
**Goal**: Implement the 4 pages per spec, using WinForms controls, pre-check recommended + Backups toggle + descriptions, progress via actual Run delegate calls (updating UI), finish with required text. Full reuse.

2.1 Create the form class (pure code, no .Designer.cs for git friendliness)  
- New file `src/McpCad.Installer/InstallerWizardForm.cs`.  
- `public partial class InstallerWizardForm : Form` (or just `class ... : Form`).  
- Constructor: `public InstallerWizardForm(McpAgent[] agents, State state, string serverPath)`.  
- Fields for the passed state/agents/serverPath + results collection.  
- Layout: simple panels (WelcomePanel, SelectionPanel, ProgressPanel, FinishPanel) toggled by visibility or a step index + method ShowStep(int). Use TableLayoutPanel or FlowLayout for simplicity. Electric orange accents where easy (ForeColor).  
- Welcome: logo lines (TextBox or Labels), explanatory text for CAD users, Next/Exit buttons.  
- Selection: CheckedListBox or list of CheckBox + Label (for description). Special handling for "CAD Skills" (always acts as multi) and "Backups" (CheckBox that does `state.BackupsEnabled = checked; update description label`). Pre-check logic: recommended names + any auto-detected. "Select All / Recommended / None" buttons optional but nice. Continue only if something useful selected.  
- Progress: ListView or DataGridView (3 columns: Agent, Status, Details). On load or "Start Install" button (or auto-start): disable nav, iterate selected, for each: update row "Running...", try { var msg = agent.Run?.Invoke(state, agent) ?? "..."; } catch..., update row OK/FAIL + msg, refresh. Use `this.BeginInvoke` or `Invoke` for UI from worker thread (Task.Run wrapper per agent or sequential on bg thread).  
- Finish: summary, results grid/list (copy style from ShowSuccessScreen), the literal next-steps paragraph ("Close & reopen your AI client(s). Keep Inventor running."), Close button that does `Application.ExitThread();` or Close + Environment.Exit(0). Optional "Open backups folder" link (Process.Start on GetBackupRoot).  
- Wire FormClosing / key preview if wanted for Escape = back/exit.  
- Title = "mcp-cad Installer", StartPosition CenterScreen, reasonable Size (e.g. 640x480 or auto).  
- **Deliverable**: New ~300-400 LOC file implementing all 4 pages + threading for progress + exact calls to existing Run / state.  
- **Test (in apply)**: Launch no-arg → see welcome → next to selection (recommended pre-checked, can toggle Backups/CAD Skills) → continue → see per-agent progress updates with real messages (incl. backup notes) → finish screen with table + exact text.

2.2 Duplicate the install loop inside the form (do NOT extract)  
- Per explicit user decision before apply: "la tui ya me agrada no se debería tocar nada".  
- Do not extract any shared runner/helper from existing TUI code (InstallSelected, RunSelectedAgentsAndExit, etc.).  
- Inside InstallerWizardForm, duplicate the small ~8-12 line selected agents execution loop (the try/catch per agent + state save + results collection).  
- This keeps the entire existing TUI/CLI code paths 100% untouched.  
- **Deliverable**: The duplication is documented in the form and in this tasks.md. No changes to Program.cs TUI sections.

2.3 Wire the form launch in the GUI path (from Phase 1 skeleton)  
- Pass the real agents/state/serverPath.  
- Remove any stub MessageBox.  
- **Deliverable**: 2-3 line change in Program.cs.

**Risk / workload for Phase 2**: Highest (the form). ~350 LOC. Core reuse verification happens here. Recommend dedicated review or chained from Phase 1.

### Phase 3: Polish, Docs, Packaging Verification, State Updates
3.1 Full docs + any final .bat/README polish  
- Ensure README quickstart leads with GUI, has "Advanced users" callout for --tui / flags.  
- Similar in docs/tools-reference.md.  
- Update any "TUI installer (Spectre.Console)" mentions to "Installer (GUI wizard or TUI)".  
- **Deliverable**: md updates.

3.2 Verify portable end-to-end (in sdd-verify, but prepare here)  
- Run publish-portable.ps1 (after all code changes).  
- On a clean test Windows machine or VM: extract zip, double-click .bat or exe → complete wizard flow for at least Claude or Cursor + CAD Skills, with Backups on → inspect %APPDATA% or ~/.cursor etc for mcp-cad entry + skills/SKILL.md copies + ~/.mcp-cad/backups/ has timestamped files → confirm no console flash or hidden properly → close wizard → run `McpCad.Installer.exe --tui` to prove TUI still there → run with --recommended to prove CLI path → success.  
- Record steps + screenshots (or describe) in verify-report.md.  
- **Deliverable**: apply-progress + verify-report notes + any tiny fixes found.

3.3 Enrich engram state + any SDD archive prep  
- Update sdd/installer-gui-wizard/state with final decisions, actual LOC, delivery choice used.  
- Ensure all openspec files present.

**Workload for Phase 3**: Low (~50 LOC + docs + manual test time).

## Review Workload Forecast Table

| Phase/Batch | Files Touched (new/changed) | Est. LOC (code) | Risk | Review Notes | Recommended Delivery |
|-------------|-----------------------------|-----------------|------|--------------|----------------------|
| 1 (csproj/Program skeleton + .bat) | McpCad.Installer.csproj (+2), Program.cs (~100), .bat (~5), 1-2 md | ~120 | Low | Pure compat + build; no user-visible GUI yet | Single small PR or first chained |
| 2 (core form + reuse) | New InstallerWizardForm.cs (~350), Program.cs glue (~20) | ~370 | Med-High | Main new logic + reuse proof; must grep for no duplication | Chained PR recommended (or size:exception if single PR) |
| 3 (polish + docs + verify prep) | README, docs/tools-reference.md, .bat polish, apply/verify md | ~30 + docs | Low | Docs + test evidence | With Batch 2 or final |
| **Total** | ~5-7 source + 4-5 SDD md | **~520** (plus SDD artifacts not counted in code budget) | ask-on-risk | Orchestrator to enforce in apply spawn | ask-on-risk (or auto-chain per cached strategy at tasks time) |

**~400 line budget awareness**: Total code ~520 is over single 400; therefore **chained PRs or explicit exception** likely. Tasks phase will record the decision from "Review Workload Forecast". Orchestrator will pass the decision explicitly when spawning sdd-apply.

**Chained PRs recommended?** Yes (user confirmed before apply: ask-on-risk + chained PRs). Current change can be one logical unit but split at apply time for review safety (3 batches as described).

## Verification Plan (for sdd-verify)
- Build + publish-portable succeeds on the branch.
- Manual portable test matrix (documented in verify-report):
  1. No-arg double-click → GUI wizard, recommended pre-selected, toggle Backups off, run, verify side-effects on disk + finish text.
  2. Same with CAD Skills only.
  3. --recommended (console path unchanged).
  4. --tui (TUI launches, full navigation + install works).
  5. --help and --agents "Cursor,Grok" (exact old behavior).
  6. TUI Backups toggle + install still works (State shared).
  7. Portable layout (exe + .bat in same dir as server) still discovers server.
  8. Backups created only when expected (quirúrgico).
- Code review: `git diff --stat`, grep for "RegisterWithSchema|InstallSkills|BackupConfigFile|FindServerPath" — only original McpAgent.cs + calls from new form/Program.
- No regression in existing success messages or next-steps.
- engram + openspec artifacts complete (state, explore, proposal, spec, design, tasks, apply-progress, verify-report).
- Proposal success criteria checklist all green.

## Risks / Blockers Carried Forward
- See design.md (csproj TFM, console hide flash, portable single-file WinForms, state path, detection heuristic).
- Workload >400 → delivery strategy decision required before full apply.
- Manual verification only (no CI for installer GUI yet).

## Next After Tasks
- User/orchestrator decision on delivery (ask-on-risk vs chained) + any scope trim.
- Spawn sdd-apply (with previous artifacts: proposal+spec+design+tasks, explicit delivery decision, TDD=false, skills paths, isolation=none or worktree if risky).
- Then sdd-verify (fresh context recommended).
- sdd-archive.

**Status of this tasks artifact**: **COMPLETE** (2026-06-12). All phases applied, verified (PASS WITH WARNINGS), archived to `openspec/changes/archive/2026-06-12-installer-gui-wizard/`.

(End of tasks.md — persisted to openspec + engram via orchestrator flow.)