# mcp-cad

<p align="center">
  <img src="logomcp.jpg" alt="mcp-cad banner" width="80%">
</p>

**Give any AI coding agent direct parametric control over desktop CAD.**  
Not an app. Not a plugin. An MCP server — infrastructure for the agent-first era of CAD.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![.NET 8](https://img.shields.io/badge/.NET-8.0-blue)](https://dotnet.microsoft.com/)
[![80+ tools](https://img.shields.io/badge/tools-80%2B-orange)](docs/tools-reference.md)
[![Release](https://img.shields.io/badge/release-v0.2.0-brightgreen)](docs/RELEASE.md)

---

## Showcase

<!-- Replace with your video: upload showcase.mp4 to the repo root, then uncomment below -->
<!-- <video src="showcase.mp4" controls width="100%"></video> -->
<!-- Alternative: animated GIF -->
<!-- ![Showcase](showcase.gif) -->

[▶️ Watch showcase video](showcase.mp4)

---

## Why mcp-cad is different

| | CAD add-ins | Browser CAD | **mcp-cad** |
|---|---|---|---|
| **Model** | Plugin (paid per seat) | Web app (SaaS) | MCP server (free, open source) |
| **Runs in** | Desktop CAD only | Browser tab | Claude, OpenCode, Cursor, Windsurf, VS Code, Pi — any agent |
| **Source** | Closed | Closed | MIT — fully open |
| **CAD engines** | Tied to one vendor | None (browser-only) | Provider-agnostic — Inventor today, SolidWorks in development, KiCad planned |
| **Control** | High-level prompts | High-level prompts | 80+ atomic tools + 22 composable skills |
| **Privacy** | Cloud-dependent | Cloud-only | Local — your data never leaves your machine |
| **Setup** | Manual per-machine | Sign up + account | Download zip + double-click installer (no git/terminal) |

### The problem with CAD AI tools today

Existing tools are **apps**. They force you into their UI, their workflow, their pricing model. CAD add-ins lock you into one vendor and charge per seat. Browser-based tools hold your designs on their servers. Both give you high-level "prompt-to-part" with limited control over the result — and zero transparency into what the AI is actually doing.

### What mcp-cad unlocks

**mcp-cad is not an app.** It's an MCP server that any AI coding agent can use as a tool. You stay in your agent (Claude, OpenCode, Cursor, Windsurf, VS Code, Pi) and the agent drives your CAD application directly — sketch by sketch, feature by feature, parameter by parameter.

- **80+ atomic tools** — not "generate a bracket", but `sketch_line`, `extrude`, `circular_pattern`, `combine`. Full parametric control.
- **Tag-based entity resolution** — name geometry `@hole_center` and reference it reliably across operations.
- **Composable skills** — higher-level abstractions built on the atomic tools, reducing tool calls for common workflows.
- **Early-bound COM** — no `dynamic`/reflection hacks. Real type safety, real reliability.
- **Provider-agnostic** — same MCP protocol and tool surface across CAD backends. Swap the engine via config, not client changes.

### Built at AI speed — 8 days, 80+ tools

The entire project was built using **SDD (Spec-Driven Development)** — AI-orchestrated planning and implementation. From first commit to 80+ production tools across sketch, 3D features, assembly, work geometry, parameters, iProperties, and export — in 8 days.

```
May 26 → Jun 3, 2026
  Sketch (20 tools)      ████████████████████
  3D Features (21)       █████████████████████
  Assembly (16)          ████████████████
  Work Geometry (3)      ███
  Params & Props (9)     █████████
  Export (4)             ████
  Skills (22)            ███████████████████████
```

---

## Quick start (easiest — for most users)

**Download and click. No git. No terminal. No .NET SDK required.**

1. Go to the [Releases page](https://github.com/Andiveli/mcp-cad/releases) and download **v0.2.0** (`mcp-cad-v0.2.0-portable.zip`)
2. Extract the zip to any folder (Desktop, Documents, etc.)
3. **Double-click `McpCad.Installer.exe`** — the GUI wizard opens immediately (no console window)
4. The **GUI wizard** opens by default (welcome → agent checkboxes + CAD Skills + Backups toggle → progress → finish). Recommended agents are pre-selected.
5. When you select **any agent** (Grok, Cursor, Claude, VS Code, OpenCode, Pi...), the installer will:
   - Register the mcp-cad MCP server for that client
   - Copy the CAD skills (`macro-basic-part`, `inventor-new-part`, `macro-selector`, ...) into that agent's skills directory (e.g. `~/.grok/skills/`, `~/.cursor/skills/`, `%APPDATA%/Claude/skills/`, etc.)
   This makes the high-level skills available natively/global to the agent.
6. The standalone "**CAD Skills**" item deploys the skills to *all* supported agents in one go.
7. **Advanced:** `McpCad.Installer.exe --tui` for the classic keyboard TUI; `--recommended` / `--all` for non-interactive CLI.

After it says configured, **restart your AI client** and open your CAD application (**Autodesk Inventor 2025+** in v0.2.0).

That's it. Your AI can now drive CAD directly.

> **Advanced:** run `McpCad.Installer.exe --tui` for the keyboard TUI, or `--recommended` / `--all` for non-interactive CLI.

---

### For developers / building from source

```powershell
git clone https://github.com/Andiveli/mcp-cad.git
cd mcp-cad

# Publish server + installer (self-contained recommended for distribution)
dotnet publish src/McpCad.Server   -c Release -r win-x64 --self-contained -p:PublishSingleFile=true -o dist/mcp-cad
dotnet publish src/McpCad.Installer -c Release -r win-x64 --self-contained -p:PublishSingleFile=true -o dist/mcp-cad

# Or use the portable release script (adds skills/, README.txt)
.\scripts\publish-portable.ps1

# Run the installer (GUI default; add -- --tui for Spectre TUI)
dotnet run --project src/McpCad.Installer
# or double-click McpCad.Installer.exe
```

**Prerequisites (dev builds):** Windows 10/11 + a supported CAD backend (Inventor 2025+ for v0.2.0) + .NET 8 SDK (only needed to build).

---

## How it works

```
You → AI Agent (Claude / OpenCode / Cursor / Windsurf / VS Code / Pi)
        │
        ├── "Create a gear with 24 teeth, module 2, 10mm thick"
        │
        ▼
     MCP Protocol (stdio)
        │
        ▼
   mcp-cad server (.NET 8)
        │
        ├── sketch_circle XY 0 0 47.5
        ├── sketch_circle XY 0 0 50 tag=@tip
        ├── extrude 1 10
        ├── circular_pattern extrusion="Extrusion1" axis="Y Axis" count=24
        └── ...
        │
        ▼
   Early-bound COM → CAD backend (Inventor in v0.2.0)
```

---

## Architecture

```
src/
├── McpCad.Core/           Protocol & models (zero COM)
├── McpCad.Inventor/        Inventor COM backend
│   ├── Managers/            Sketch, Feature, Assembly, Parameter, Property, Export
│   └── Helpers/              TagStore, AxisResolver, EdgeResolver, ComDispatch
├── McpCad.Tools/           MCP tool definitions (AtomicTools, SkillTools)
├── McpCad.Server/          MCP stdio transport
└── McpCad.Installer/       Installer (GUI wizard default + Spectre TUI via --tui)
```

**Provider pattern** — same protocol, multiple CAD engines:

```
MCP → ICadProvider (connection, docs, export)
       ├── IMechanicalCadProvider (sketch, 3D, assembly)
       │   ├── InventorProvider (COM)          ← v0.2.0 release
       │   └── SolidWorksProvider (in development)
       └── IElectronicCadProvider
           └── KiCadProvider (planned)
```

---

## Full tool reference

See [docs/tools-reference.md](docs/tools-reference.md) for the complete list of 80+ tools and 22 composable skills.

---

## Tags

Tag sketch entities with `@name` for reliable referencing:

```
sketch_line 0 -1 0 5 tag=eje     →  revolve profile 1 axis=@eje
sketch_circle 3 0 1 tag=perfil   →  extrude profile=@perfil
```

---

## Reliability through feedback

After performing operations, the agent should request feedback to verify the actual state in your CAD application (close the loop).

mcp-cad supports two complementary approaches:
- **Visual/multimodal**: `capture_viewport_image` returns Base64 PNG screenshots from standard views (Iso, Front, Top, Right, "Current", etc.). Vision models can directly inspect geometry, bosses, grooves, crown shape, etc.
- **Structured data**: `get_feature_tree` (feature tree / Árbol de Operaciones), `get_bounding_box`, and `inspect_edges` give exact names, structure, and measurements without relying on vision.

See the [Inspection & Verification section](docs/tools-reference.md#inspection--verification) in the tool reference for details and recommended patterns.

---

## Releases

| Version | Highlights |
|---------|------------|
| **[v0.2.0](docs/RELEASE.md#v020)** | GUI installer wizard, portable self-contained package, CAD skills deploy, config backups |
| [v0.1.0](docs/RELEASE.md#v010) | Initial public release — 80+ Inventor tools, TUI installer, MIT |

Full changelog and publishing instructions: [docs/RELEASE.md](docs/RELEASE.md)

---

## License

MIT — free, forever.