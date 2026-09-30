# Releases

## v0.2.0

**Date:** 2026-06-12  
**CAD backend:** Autodesk Inventor 2025+ (production). SolidWorks provider in active development on a separate branch.

### Highlights

- **GUI installer wizard** — default experience on double-click `McpCad.Installer.exe`. Welcome → agent selection + CAD Skills + Backups → progress → finish.
- **Portable self-contained package** — two single-file executables (`McpCad.Server.exe`, `McpCad.Installer.exe`) with no .NET SDK required on the end-user machine.
- **CAD skills deploy** — installer copies bundled skills (`macro-basic-part`, `inventor-new-part`, `macro-selector`, …) into each selected agent's global skills directory.
- **Config backups** — optional surgical backup of MCP config files before overwrite (toggle in GUI).
- **Multi-CAD copy** — installer and portable README use CAD-neutral language; backend selection via provider config is coming with the SolidWorks release.
- **TUI preserved** — `McpCad.Installer.exe --tui` for keyboard navigation; `--recommended` / `--all` for non-interactive CLI.

### Download

1. Get `mcp-cad-v0.2.0-portable.zip` from [GitHub Releases](https://github.com/Andiveli/mcp-cad/releases/tag/v0.2.0).
2. Extract anywhere.
3. Double-click `McpCad.Installer.exe`.
4. Restart your AI client and open Inventor.

### Package contents

```
mcp-cad-v0.2.0-portable/
├── McpCad.Server.exe       # MCP server (Inventor backend)
├── McpCad.Installer.exe    # GUI wizard (default) + TUI/CLI flags
├── skills/                 # CAD skills deployed by installer
├── appsettings.json        # Server config (Cad provider defaults to Inventor)
└── README.txt              # End-user quick instructions
```

### Building the portable package (maintainers)

From the repo root on `main`:

```powershell
.\scripts\publish-portable.ps1
```

This writes to `dist/mcp-cad-portable/`. Zip that folder as `mcp-cad-v0.2.0-portable.zip` and attach to the GitHub release.

To tag and publish (when ready):

```powershell
git tag -a v0.2.0 -m "v0.2.0: GUI installer, portable package, CAD skills deploy"
git push origin v0.2.0
```

Then create the release on GitHub with the zip asset and these notes.

### Upgrade from v0.1.0

1. Download the new portable zip.
2. Extract to a new folder (or overwrite an old install).
3. Re-run `McpCad.Installer.exe` — the wizard re-registers MCP paths and redeploys skills.
4. Restart your AI client.

No manual JSON editing required.

---

## v0.1.0

**Date:** 2026-06-03  
**Tag:** `v0.1.0`

Initial public release:

- 80+ atomic MCP tools for Autodesk Inventor (sketch, 3D, assembly, work geometry, parameters, iProperties, export).
- 22 composable skills.
- Spectre.Console TUI installer.
- Tag-based entity resolution (`@name`).
- Inspection tools: `capture_viewport_image`, `get_feature_tree`, `get_bounding_box`, `inspect_edges`.
- MIT license.

---

## Roadmap (post v0.2.0)

- **SolidWorks provider** — config-driven `Cad:Provider` selection, `cad_connect` / `cad_health` / `cad_disconnect` as primary connection tools with `inventor_*` aliases for backward compatibility.
- **KiCad** — electronic CAD provider (planned).