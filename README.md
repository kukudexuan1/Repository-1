# Evidence-Constrained Multi-Agent Framework for Auditable Mechanical Design

**An Evidence-Constrained Multi-Agent Framework Driven by LLM for Auditable Mechanical Design with Closed-Loop Design–Analysis Verification**

[![License](https://img.shields.io/badge/license-MIT--and--GPL--3.0-lightgrey.svg)](#license)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![.NET 8](https://img.shields.io/badge/.NET-8.0-512BD4.svg)](https://dotnet.microsoft.com/)
---

## Overview

This repository implements an LLM-driven multi-agent framework for **auditable mechanical design**. A FastAPI orchestration backend coordinates a set of role-based agents and two local Model Context Protocol (MCP) servers — one for parametric CAD (Autodesk Inventor) and one for finite-element analysis (ANSYS Workbench). Every design parameter, formula lookup and calculation is recorded in an evidence ledger; dependency-driven invalidation, hard gates and interrupt recovery enforce a closed **CAD → CAE → verification** loop.

The repository contains the orchestration backend, both (modified) MCP servers, the experimental harness (E0–E5) with the full run outputs, and the two engineering case studies **including solved results**.

---

## Repository structure

```text
.
├── LICENSE                      # MIT, covering the original backend/experiments/test
├── THIRD-PARTY-NOTICES.md       # provenance, licenses and list of modified MCP files
├── README.md  .gitignore
│
├── backend/                     # FastAPI orchestration backend + static web UI
│   ├── app/                     # adapters/ agent/ api/ core/ mcp/ schemas/ services/
│   │   ├── main.py              #   ASGI app (REST + MCP lifespan)
│   │   └── frontend_launcher.py #   one-command backend + browser launcher
│   ├── frontend/                # static web UI (index.html, app.js, ...)
│   ├── scripts/  tests/
│   ├── workspace/               # session workspace & reports (design_sessions.db excluded)
│   ├── logs/
│   ├── schema.sql  requirements.txt  pytest.ini  .env.example
│
├── mcp-cad/                     # .NET 8 MCP server — parametric control of Inventor
│   ├── src/
│   │   ├── McpCad.Core/         #   protocol & models (no COM)
│   │   ├── McpCad.Inventor/     #   Inventor early-bound COM backend
│   │   ├── McpCad.Tools/        #   atomic tools + composable skills
│   │   ├── McpCad.Server/       #   MCP stdio transport
│   │   └── McpCad.Installer/    #   GUI/TUI installer
│   ├── tests/  openspec/  docs/  skills/  scripts/
│   ├── mcp-cad.sln  README.md  LICENSE      # LICENSE = GPL-3.0
│
├── ANSYS-Workbench-mcp/         # Python (FastMCP) server — bridges ANSYS Workbench
│   ├── mcp_server.py
│   ├── ansys_workbench_bridge.wbjn
│   ├── commands/  scripts/  runs/  results/
│   ├── requirements.txt  .mcp.json  README.md  LICENSE   # LICENSE = MIT
│
├── experiments/                 # experimental framework and reproduction
│   ├── framework/               # run manager, conditions, gold standard, metrics
│   ├── analysis/                # aggregation, statistical tests, effect sizes
│   ├── dataset/task_specs/      # 35 task specifications (B/G/R/S)
│   ├── config/                  # base.yaml, conditions.yaml, dataset.yaml
│   ├── tables/
│   ├── E0_environment/  E1_knowledge_retrieval/  E2_units_formula/
│   ├── E4_invalidation/  E5_gates/
│   ├── results/                 # full per-run outputs (versioned)
│   └── pyproject.toml
│
└── test/                        # two CAD–CAE case studies (solved results included)
    ├── 1/                        # Case 1: simple machined part
    └── reducer/                  # Case 2: single-stage cylindrical-gear reducer
```

---

## How it works

```text
                         ┌──────────────────────────────┐
                         │      Web UI (static)         │
                         └──────────────┬───────────────┘
                                        │ HTTP / SSE
                         ┌──────────────▼───────────────┐
                         │   backend (FastAPI)          │
                         │  role agents · evidence      │
                         │  ledger · gates · recovery   │
                         └───┬──────────────────────┬────┘
                  MCP/stdio  │                      │  MCP/stdio
                  ┌──────────▼─────────┐  ┌─────────▼──────────────┐
                  │ mcp-cad (.NET 8)   │  │ ANSYS-Workbench-mcp    │
                  │ early-bound COM    │  │ (Python FastMCP)       │
                  └──────────┬─────────┘  └─────────┬──────────────┘
                             ▼                      ▼
                  Autodesk Inventor          ANSYS Workbench
                  (parametric CAD)           (Mechanical / MAPDL)
```

- **mcp-cad** drives Inventor feature-by-feature (sketches, extrusions, patterns, assemblies, export) through atomic tools.
- **ANSYS-Workbench-mcp** exchanges command/result files with a Workbench journal over a file-based IPC queue, creating analysis systems, meshing and solving, then returning results.
- The **backend** records every parameter source and calculation, propagates invalidation when upstream values change, and enforces gates before stage transitions.

---

## Prerequisites

- **Windows 10/11** (the CAD/CAE automation uses Windows-only COM and the ANSYS toolchain).
- **Python 3.11+** (for `backend`, `ANSYS-Workbench-mcp`, `experiments`).
- **.NET 8 SDK** — needed to build `mcp-cad` from source.
- **Autodesk Inventor 2025 or newer**.
- **ANSYS Workbench 2025 R1 / R2** (v251 / v252); adjust the executable paths in the configuration to your installed version.
- LLM API access:
  - **DeepSeek** API key — main orchestration model.
  - **Alibaba DashScope** API key — Qwen coding / vision / math model slots.

---

## Installation

### 1. Build the CAD MCP server (mcp-cad)

The backend launches the **compiled executable** of mcp-cad (do **not** use `dotnet run`, because MSBuild logs on stdout would corrupt the JSON-RPC stream).

```powershell
cd mcp-cad
dotnet build src/McpCad.Server -c Release
```

The server executable is produced at:

```text
src/McpCad.Server/bin/Release/net8.0-windows/McpCad.Server.exe
```

> `bin/` and `obj/` are intentionally not versioned (regenerate with the command above). For a self-contained distributable, see `mcp-cad/README.md`.

### 2. Configure the backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env
```

Edit `backend/.env` and fill in:

- the DeepSeek and DashScope API keys;
- `MCPCAD_COMMAND` — absolute path to the compiled `McpCad.Server.exe`;
- the `ANSYS_*` executable paths matching your local ANSYS version;
- `ANSYS_WORKBENCH_MCP_SCRATCH` — an **ASCII-only** scratch directory. Mechanical rejects non-ASCII paths, so this is required when the project path contains Chinese characters.

> The local `.env` files are **never committed** (they hold real API keys). Only `.env.example` templates are versioned.

### 3. ANSYS MCP standalone configuration (optional)

`ANSYS-Workbench-mcp` can run independently for any MCP client; its registration is in `.mcp.json`. Adjust the `ANSYS_*` paths there if needed, then `pip install -r requirements.txt`.

---

## Running the system

From the `backend/` directory:

```powershell
python -m app.frontend_launcher
# options: --host 127.0.0.1 --port 8000 --no-browser
```

This starts uvicorn, launches the configured MCP servers (first start takes 1–2 minutes), and opens the UI at <http://127.0.0.1:8000/index.html>. Health check: <http://127.0.0.1:8000/health>.

Alternatively, run the API only:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Windows users can double-click `启动前端.bat`, which uses the `edp` conda environment when available.

---

## Reproducing the experiments

The experiment harness talks to a **running backend** (default `http://localhost:8000`).

```powershell
cd experiments
pip install -e .
```

Create `experiments/.env` (not versioned) with at least:

```dotenv
BACKEND_URL=http://localhost:8000
BEXT_ENDPOINT=https://dashscope.aliyuncs.com/compatible-mode/v1
BEXT_API_KEY=your_dashscope_api_key
BEXT_MODEL=deepseek-v4-pro
BEXT_TEMPERATURE=0.0
EXP_N_REPLICATES=5
EXP_RANDOM_SEED=42
EXP_RESULTS_DIR=results
ANNOTATOR_1_ID=annotator_A
ANNOTATOR_2_ID=annotator_B
```

With the backend running:

```powershell
python E0_environment/run_e0.py
python E1_knowledge_retrieval/run_e1.py
python E2_units_formula/run_e2.py
python E4_invalidation/run_e4.py
python E5_gates/run_e5.py
```

Per-run outputs are written under `experiments/results/` and are **already included in this repository**, so the reported campaigns can be audited without re-running. Re-running adds new run directories.

Aggregate and analyze (these read `results/` and write into `analysis/`):

```powershell
python analysis/aggregate_results.py     # -> analysis/*_runs_corrected.csv
python analysis/statistical_tests.py     # bootstrap CIs, Wilcoxon, Holm correction
python analysis/effect_sizes.py          # Cliff's delta / effect-size tables
python analysis/show_e1_results.py
```

The controlled conditions are defined in `experiments/config/conditions.yaml`; fixed settings are in `config/base.yaml`.

---

## CAD–CAE case studies (`test/`)

Two case studies are distributed with full CAD sources, the complete ANSYS project state (mesh, contacts, loads, constraints) **and the solved result files**:

| Case | CAD | ANSYS project |
|---|---|---|
| `test/1/` — simple machined part | `1.ipt`, `1.stp` | `1.wbpj` + `1_files/` |
| `test/reducer/` — single-stage cylindrical-gear reducer | `assemble.iam/.stp`, `assemble_1.iam/.stp`, component `.ipt`, `设计加速器/` sub-assemblies | `reducer.wbpj` + `reducer_files/` |

The Workbench folders retain the Mechanical model database (`*.mechdb`), solver deck (`ds.dat`), engineering-data/material definitions (`*.engd`, `EngineeringData.xml`, `MatML.xml`), operation journals (`journal1.wbjn`) **and the result files (`file.rst`)**. Opening the `.wbpj` therefore loads the already-solved state; no re-solve is required to inspect the reported results. Exported reducer result tables are provided as `reducer/等效应力.txt` and `reducer/总变形.txt`.

To regenerate from scratch: open the `.wbpj`, confirm geometry links resolve to the co-located `.ipt/.stp` (use an ASCII-only scratch folder if prompted), then **Mesh → Solve**.

> `test/2/` and `test/4/` are development intermediates and are intentionally excluded; only cases `1` and `reducer` correspond to the reported studies. `OldVersions/` (Inventor automatic backups) are also excluded because git provides version history.

---

## Data availability

**Almost everything is contained in this git repository** — source code, both modified MCP servers, the experiment framework, all per-run experiment outputs, aggregated tables, and the two case-study engineering projects including solved `file.rst` results. No external data archive (e.g. Zenodo) is required. The non-versioned items are: regenerable build/cache outputs (`bin/`, `obj/`, `__pycache__/`, virtual environments), the local `.env` secret files, and the backend session database `backend/workspace/design_sessions.db`, which holds private session data and is created from `schema.sql` on first run. The arXiv paper link will be added after submission.

---

## Tests

```powershell
cd backend;  pytest
cd experiments;  pytest
cd mcp-cad;  dotnet test
```

---

## License

This is a single repository with multiple licenses; see **[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)** for details.

- **Original work** (`backend/`, `experiments/`, `test/`): **MIT License** — root [LICENSE](LICENSE), Copyright (c) 2026 `kukudexuan1`.
- **ANSYS-Workbench-mcp/**: **MIT License**, Copyright (c) 2026 hongwenwang36-eng; modified files retain the MIT License.
- **mcp-cad/**: **GNU General Public License v3.0 (GPL-3.0-only)**. The upstream README shows an MIT badge, but its `LICENSE` file (and GitHub detection) is GPL-3.0, which is treated as governing. Modifications and added files remain under GPL-3.0 and carry SPDX notices.

The backend invokes mcp-cad strictly as a **separate process over MCP (stdio)** without linking or incorporating its code; this is intended to be an aggregation of independent programs, leaving the original work under MIT. ANSYS® and Autodesk Inventor® are trademarks of their respective owners; this project is not affiliated with either vendor.


---

