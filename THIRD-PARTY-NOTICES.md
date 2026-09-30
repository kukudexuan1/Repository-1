# Third-Party Notices

This repository incorporates two third-party open-source MCP (Model Context
Protocol) servers, each modified by the repository author (`kukudexuan1`,
2026). This file records their provenance, licenses and the exact files that
were changed or added. The precise change dates and authorship are also
recorded by the git history; commit with your real git identity.

| Component | Directory | License | Upstream |
|---|---|---|---|
| ANSYS-Workbench-mcp | `ANSYS-Workbench-mcp/` | **MIT** | https://github.com/hongwenwang36-eng/ANSYS-Workbench-mcp |
| mcp-cad | `mcp-cad/` | **GPL-3.0-only** | https://github.com/Andiveli/mcp-cad |

---

## 1. ANSYS-Workbench-mcp — MIT License

Copyright (c) 2026 hongwenwang36-eng. The full MIT License is in
`ANSYS-Workbench-mcp/LICENSE`. The component was modified; under the MIT
License the original copyright notice and license text are retained.

**Modified files**

- `.mcp.json`
- `ansys_workbench_bridge.wbjn`
- `mcp_server.py`
- `mcp.log`
- `status.json`

**Deleted**

- `results/f92da5dd.json`

**Added files**

- `_e2e_mech.py`
- `results/0eda4a25.json`
- `results/1e334b07.json`
- `results/1fc56a9f.json`
- `results/3202703b.json`
- `results/4377a7ce.json`
- `results/460cebe3.json`
- `results/46f317b4.json`
- `results/4d054f22.json`
- `results/6fbfe486.json`
- `results/7aeab5f2.json`
- `results/932107b7.json`
- `results/cd2dc43b.json`
- `results/cfdae6ef.json`
- `runs/_stepprobe/`
- `runs/mech_e2e/`

---

## 2. mcp-cad — GNU General Public License v3.0 (GPL-3.0-only)

The full GPL-3.0 text is in `mcp-cad/LICENSE`. The upstream README and badges
state "MIT", but the actual `LICENSE` file is the GPL-3.0 text and GitHub's
license detection reports **GPL-3.0**; GPL-3.0 is therefore treated as the
governing license.

Per GPL-3.0 section 5, modified and added files carry prominent notices. The
newly added source files carry an `SPDX-License-Identifier: GPL-3.0-only`
header; the modified pre-existing files are listed below, and authorship and
dates are recorded in the git history.

**Modified pre-existing files**

- `src/McpCad.Core/IMechanicalCadProvider.cs`
- `src/McpCad.Inventor/InventorProvider.cs`
- `src/McpCad.Inventor/Managers/AssemblyManager.cs`
- `src/McpCad.Inventor/Managers/InspectionManager.cs`
- `src/McpCad.Inventor/Managers/SketchManager.cs`
- `src/McpCad.Inventor/Managers/WorkFeatureManager.cs`
- `src/McpCad.Inventor/McpCad.Inventor.csproj`
- `src/McpCad.Tools/AtomicTools.cs`
- `tests/McpCad.Tests/Integration/ComConnectionTests.cs`
- `tests/McpCad.Tests/Integration/FeatureIntegrationTests.cs`
- `tests/McpCad.Tests/Integration/SketchIntegrationTests.cs`
- `tests/McpCad.Tests/McpCad.Tests.csproj`

**Added files (GPL-3.0-only; SPDX-tagged)**

- `src/McpCad.Inventor/Managers/DeterministicFeatureManager.cs`
- `tests/McpCad.Tests/Integration/InventorFactAttribute.cs`
- `tests/McpCad.Tests/Integration/InventorIntegrationCollection.cs`
- `test_new_tools.py`

### GPL scope and process boundary

The backend invokes mcp-cad as a **separate operating system process** and
communicates with it over MCP using stdio (JSON-RPC). It is not statically or
dynamically linked to mcp-cad and does not incorporate GPL-licensed source
into its own modules. This loose, arm's-length coupling is intended to be an
**aggregation of independent programs**, so the original backend, experiments
and case-study materials are not placed under GPL-3.0. The entire,
corresponding source of mcp-cad (including modifications) is provided in
`mcp-cad/`, satisfying the GPL-3.0 source-disclosure obligations.

---

## Trademarks

"ANSYS", "Autodesk" and "Inventor" are trademarks of their respective owners.
The licenses above do not grant any trademark rights, and the bundled
components are not affiliated with or endorsed by ANSYS, Inc. or Autodesk,
Inc. Do not use the upstream authors' or projects' names to imply endorsement.

---

## Before publishing

- Replace every `kukudexuan1` placeholder (in this file, the root `LICENSE`,
  and the SPDX-tagged new files) with the correct copyright holder name.
- For maximum GPL-3.0 clarity, you may additionally add an SPDX/change notice
  to the header of each "modified pre-existing file" listed above.
- Commit using a consistent, real `user.name` / `user.email` so the git history
  documents the modifications and their dates.
