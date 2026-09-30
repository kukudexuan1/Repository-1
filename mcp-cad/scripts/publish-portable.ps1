<#
.SYNOPSIS
  Builds a clean, end-user portable package for mcp-cad.

  Produces dist/mcp-cad-portable/ containing:
    - McpCad.Server.exe (self-contained)
    - McpCad.Installer.exe (self-contained)
    - All required runtime DLLs + appsettings.json
    - A small README.txt

  Then you can zip that folder and upload to GitHub Releases.

  Usage (from repo root):
    .\scripts\publish-portable.ps1
#>

param(
    [string]$Configuration = "Release",
    [string]$OutputRoot = "dist/mcp-cad-portable"
)

$ErrorActionPreference = "Stop"

Write-Host "=== mcp-cad portable package builder ===" -ForegroundColor Cyan

# Clean previous
if (Test-Path $OutputRoot) {
    Remove-Item $OutputRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $OutputRoot | Out-Null

Write-Host "Publishing McpCad.Server (self-contained single-file)..."
dotnet publish src/McpCad.Server `
    -c $Configuration `
    -r win-x64 `
    --self-contained true `
    -p:PublishSingleFile=true `
    -p:IncludeNativeLibrariesForSelfExtract=true `
    -o "$OutputRoot" | Out-Host

Write-Host "Publishing McpCad.Installer (self-contained single-file)..."
dotnet publish src/McpCad.Installer `
    -c $Configuration `
    -r win-x64 `
    --self-contained true `
    -p:PublishSingleFile=true `
    -p:IncludeNativeLibrariesForSelfExtract=true `
    -o "$OutputRoot" | Out-Host

# Copy the CAD skills (SKILL.md files) so the installer can deploy them as global skills for Grok
if (Test-Path "skills") {
    Copy-Item "skills" -Destination (Join-Path $OutputRoot "skills") -Recurse -Force
    Write-Host "Copied skills/ (for global Grok skill installation)"
}

# Copy a minimal user readme
$readme = @"
mcp-cad - AI control for parametric CAD (MCP server)

EASIEST WAY:
  Double-click McpCad.Installer.exe

  The GUI wizard will register mcp-cad with your AI tools (Claude Desktop, Cursor, etc.).

REQUIREMENTS:
  - Windows 10/11
  - A supported CAD application (Inventor or SolidWorks) running when the AI uses tools

After installation:
  1. Fully close and reopen your AI client (especially Grok).
  2. Open your CAD application (Inventor or SolidWorks).
  3. Talk to your AI: "Create a 80x60mm plate with 4 holes..."

When you select any agent (Grok, Cursor, Claude, VS Code, etc.), the installer now:
- Registers the mcp-cad MCP server for that client
- Copies the CAD skills (macro-basic-part, inventor-new-part, macro-selector, ...)
  into that agent's skills directory (e.g. ~/.grok/skills/, ~/.cursor/skills/, %APPDATA%/Claude/skills/, etc.)
  so the high-level skills become available globally/native to the agent.

You can also select the "CAD Skills" item to deploy them to every supported agent at once.

For updates: download a newer portable zip, extract over the old folder or to a new location, and re-run the installer.

More info: https://github.com/Andiveli/mcp-cad
"@

$readme | Out-File -Encoding UTF8 -FilePath (Join-Path $OutputRoot "README.txt")

# Remove heavy debug files from the portable folder to keep size down
Get-ChildItem $OutputRoot -Filter "*.pdb" -Recurse | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem $OutputRoot -Filter "*.deps.json" -Recurse | Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "=== Portable package ready ===" -ForegroundColor Green
Write-Host "Location: $OutputRoot"
Write-Host "Zip this folder (or its contents) for GitHub Releases."
Write-Host ""
Write-Host "Tip: The two .exe files are now self-contained - end users do not need to install .NET 8."
