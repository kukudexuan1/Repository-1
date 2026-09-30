# Specification: GUI Wizard for McpCad.Installer (installer-gui-wizard)

**Change**: installer-gui-wizard  
**Derived from**: proposal.md (this dir), explore report (engram sdd/installer-gui-wizard/explore), task engram #257, session #258, sdd-init/mcp-cad, current implementation in src/McpCad.Installer/* + packaging + docs.  
**Language**: English (technical).  
**Style**: GIVEN / WHEN / THEN acceptance scenarios + requirements. Covers functional, compatibility, UX, packaging, and verification.

## Purpose
Define the formal requirements for adding a Windows Forms GUI wizard inside McpCad.Installer so that non-technical Autodesk Inventor users can use the "download portable zip + double-click" flow without any terminal or TUI interaction, while the existing Spectre TUI, all CLI flags, .bat behavior (with updates), portable packaging, skills deployment, quirúrgico backups, and centralized registration logic remain 100% compatible and functional.

## Requirements

### Requirement: GUI Launch by Default for End-User Flow
The installer MUST launch the WinForms GUI wizard (instead of TUI or plain console) when invoked with zero command-line arguments from a typical Explorer double-click (or equivalent "no console intent" launch).

#### Scenario: Double-click McpCad.Installer.exe or McpCad-Install.bat (no args)
- GIVEN the portable package is extracted and the user double-clicks McpCad.Installer.exe (or the .bat which launches the exe with no extra args)
- WHEN the process starts with args.Length == 0 and no explicit TUI/CLI intent
- THEN a WinForms wizard window MUST appear (console window SHOULD be hidden via P/Invoke or equivalent; no Spectre TUI rendering)
- AND the wizard MUST present classic pages (welcome, selection, progress, finish)

#### Scenario: CLI flags still force non-GUI paths
- GIVEN any of --recommended, --all, --agents, --help, -h, --install-recommended, --install-all (or --tui for explicit TUI)
- WHEN launched with those args (from .bat, script, or terminal)
- THEN the original non-interactive console paths or TUI MUST execute exactly as before this change (no GUI window created)

### Requirement: Wizard Pages and UX
The GUI MUST implement a linear wizard with the following pages, using standard WinForms controls for accessibility and simplicity.

#### Scenario: Welcome page
- GIVEN the GUI starts
- WHEN the welcome page is shown
- THEN it MUST display mcp-cad branding/logo (reuse text or simple graphic consistent with current ASCII), a short non-technical explanation ("Connect your AI tools to Autodesk Inventor. No terminal needed."), and prominent "Get Started" / "Next" button.
- AND "Exit" / "Cancel" must be available.

#### Scenario: Agent selection page (core UX)
- GIVEN the selection page
- WHEN rendered
- THEN it MUST show a list or panel of checkboxes for all supported agents: OpenCode, Claude, Pi, VS Code, Cursor, Grok, plus special items "CAD Skills" (description: "Install CAD skills to ALL supported agents' skills directories at once") and "Backups" (toggle, default enabled, description matching current: "Enabled — press to disable (recommended for safety)" or equivalent checkbox/label).
- AND the recommended set (Claude, Cursor, Grok, OpenCode, CAD Skills) MUST be pre-checked by default.
- AND auto-detect behavior from current code (pre-select agents whose config dirs exist) SHOULD be applied where practical (reuse McpAgents.All + logic).
- AND descriptions for each must be visible (from current McpAgent.Description).
- AND user MUST be able to toggle any, including the Backups checkbox (which updates in-memory State.BackupsEnabled equivalent).
- AND "Back", "Continue" (only enabled if >=1 real agent selected or CAD Skills), "Exit" buttons present.  
- Back button MUST be functional (user decision before apply).
- AND defaults + State prefs respected for one-click experience.

#### Scenario: Progress page
- GIVEN user clicks Continue on selection with some agents selected
- WHEN the install phase runs (reusing existing Run delegates)
- THEN a progress UI MUST be shown (e.g. ListView or DataGrid with columns Agent | Status | Details, or per-row ProgressBar + label).
- AND for each selected agent the UI MUST update in real-time or sequentially with status messages (e.g. "Configuring...", "CAD skills installed...", success/fail, backup info if any) while the shared registration + skills + backup logic executes.
- AND the underlying calls MUST be exactly the same as current InstallSelected / RunSelectedAgentsAndExit (no duplication of RegisterWithSchema, InstallSkills, BackupConfigFile, etc.).
- AND errors per agent are captured and shown (do not abort the whole run).

#### Scenario: Finish page
- GIVEN the install phase completes for the selection
- WHEN the finish screen appears
- THEN it MUST show a clear summary (success count, table or list of results with agent + status + details, mirroring current ShowSuccessScreen table).
- AND the exact next-steps text (or close variant) MUST be displayed: "Close & reopen your AI client(s). Keep Inventor running."
- AND buttons: "Close" (or "Finish"), optional "View backups folder" or "Open logs" if applicable.
- AND on Close the app exits cleanly (0 or appropriate code).

### Requirement: 100% Backend Reuse and No Duplication
All registration, skills deployment, backup, discovery, and state logic MUST be performed by calling the existing centralized code in McpAgent.cs / McpAgents.

#### Scenario: GUI invokes registration for an agent
- GIVEN a user selection in the GUI
- WHEN the Continue action triggers install
- THEN for each selected McpAgent the code MUST obtain the agent via McpAgents.All(state), set Selected if needed, resolve serverPath = McpAgents.GetResolvedServerPath(), and invoke the agent's Run delegate (or equivalent shared runner) exactly as the TUI and non-int paths do today.
- AND quirúrgico backups (config always if enabled + file exists; skills only if target dir pre-existed), skills copy (to per-agent dirs + CAD Skills to all), Grok Tomlyn special case, JSON merge via ConfigManager, State save, portable Find* paths — all MUST behave identically (same side effects, same messages/return strings, same backup locations under ~/.mcp-cad/backups/).

#### Scenario: CAD Skills and Backups items
- GIVEN "CAD Skills" selected (alone or with others)
- WHEN executed
- THEN it MUST call the exact InstallSkillsToAllAgents(state) path.
- GIVEN the Backups checkbox is toggled in GUI
- THEN State.BackupsEnabled equivalent is updated and respected by the shared backup methods on the next run.

### Requirement: Compatibility with Existing TUI, CLI, .bat, Packaging, State, Docs
No existing behavior for advanced users or automation may regress.

#### Scenario: All current CLI flags and non-int paths
- GIVEN launch with --recommended (or --all, --agents "Claude,Cursor", --help)
- WHEN executed (from .bat, PowerShell, cmd, or double-click with args)
- THEN output, side effects, success messages, error handling, and exit codes MUST be identical to pre-change behavior (RunSelectedAgentsAndExit etc.).

#### Scenario: Interactive TUI remains fully functional
- GIVEN launch with --tui (new) or future detection that forces TUI, or in contexts where GUI is inappropriate
- WHEN the TUI path runs
- THEN the full Spectre logo, navigation (j/k/arrows/Space/Enter on agents + Backups + Continue/Exit), auto-detect, status messages, success table, and all key handling MUST work exactly as today.

#### Scenario: McpCad-Install.bat default changes safely
- GIVEN the updated .bat (launches exe with no args for new GUI default)
- WHEN a user double-clicks the .bat from a fresh portable zip
- THEN the GUI wizard appears (recommended pre-selected).
- AND if user passes args to .bat or uses --tui variant, the documented advanced path works.
- AND existing users who pinned the .bat see the new (better) default without breakage.

#### Scenario: Portable packaging unchanged in substance
- GIVEN `scripts/publish-portable.ps1` run (with any minimal updates for WinForms)
- WHEN the dist/mcp-cad-portable zip is produced and extracted on clean Windows
- THEN both exes are present and self-contained, .bat + skills/ copied, README.txt generated, and double-clicking the .bat or exe yields the GUI wizard (or CLI if flagged).

#### Scenario: State persistence
- GIVEN runs of GUI or TUI (portable or dev)
- THEN BackupsEnabled and other prefs in State are respected across modes where applicable (current "scripts/tui/state.json" path or robust equivalent; loads/saves do not regress).

#### Scenario: Documentation updates
- GIVEN README.md and docs/tools-reference.md updated
- WHEN a new user reads the quickstart
- THEN the primary instructions lead with "Double-click McpCad-Install.bat — the GUI wizard will guide you" (with screenshots or clear description of pages).
- AND a note or section exists: "Advanced / scripting / terminal users: use McpCad.Installer.exe --tui or the CLI flags (--recommended, --agents ...)".

### Requirement: Technical Implementation Constraints
- Must use WinForms (System.Windows.Forms) added to the McpCad.Installer project.
- csproj TargetFramework MUST become net8.0-windows (or equivalent that enables WinForms while keeping single-file self-contained win-x64 publish).
- <UseWindowsForms>true</UseWindowsForms> and proper STAThread entry for the GUI path.
- The change MUST keep the app self-contained and portable (no external .NET install required for end users).
- Console hiding for pure GUI launches (P/Invoke on kernel32 GetConsoleWindow + ShowWindow) is acceptable and expected for good UX.
- All new GUI code lives inside src/McpCad.Installer (new forms / partial classes / Gui/ folder ok).
- No changes to McpCad.* other projects.

### Requirement: Verification & Non-Regression
- The full pipeline (apply + verify) MUST include manual end-to-end test of the portable package on Windows (extract, double-click, select/customize, run, verify config + skills files + optional backup, restart "AI client" simulation, confirm TUI still works with --tui, all flags produce expected console behavior).
- No automated xUnit coverage required for the GUI itself (installer is UX tool); server/tool tests remain unaffected.
- Code review must confirm zero duplication of backend logic (static calls only to McpAgents.* , ConfigManager, etc.).

### Non-Requirements (Explicit)
- No new agents or skills.
- No changes to MCP server or Inventor COM code.
- No cross-platform GUI or Linux support.
- No removal of any existing TUI/CLI code paths.
- No requirement for "Back" navigation in wizard if linear is simpler (but recommended if easy).
- No i18n or theming beyond functional simplicity matching target CAD users.

## Acceptance
A change is complete only when all "MUST" requirements above have passing scenarios (verified in sdd-verify), the explore/design constraints are honored, proposal success criteria are met, and the hybrid artifacts (this spec + design + tasks + apply-progress + verify-report) exist in openspec + engram state.

**References**: proposal.md, explore (engram), task #257, session #258, current McpAgent.cs / Program.cs / packaging, tui-installer archived specs (for continuity of "recommended", backups toggle, skills, portable discovery).