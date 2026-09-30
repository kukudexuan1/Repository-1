using System.Runtime.InteropServices;
using System.Windows.Forms;
using Spectre.Console;

// Resolve Spectre.Console.Color after net8.0-windows brings System.Drawing.Color into scope.
using Color = Spectre.Console.Color;

namespace McpCad.Installer;

public class Program
{
    private const string StatePath = "scripts/tui/state.json";
    private static State _state = new();
    private static McpAgent[] _agents = [];
    private static int _selectedIdx;
    private static string _status = "";

    // Electric orange for the TUI
    private const string ElectricOrange = "bold #FF5F00";

    // Simple ASCII name only (as before the banner image request)
    private static readonly string[] LogoLines = new[]
    {
        " __  __  ____  ____     ____    _    ____ ",
        "|  \\/  |/ ___||  _ \\   / ___|  / \\  |  _ \\ ",
        "| |\\/| | |    | |_) | | |     / _ \\ | | | |",
        "| |  | | |___ |  __/  | |___ / ___ \\| |_| |",
        "|_|  |_|\\____||_|      \\____/_/   \\_\\____/ ",
        "",
        "                 MCP-CAD"
    };

    [STAThread]
    public static void Main(string[] args)
    {
        _state = State.Load(StatePath);
        _agents = McpAgents.All(_state);
        AutoDetectAgents(_agents);

        // Resolve server path early (used for both non-interactive and to display in TUI)
        var serverPath = McpAgents.GetResolvedServerPath();

        // --- Non-interactive / one-click support for "download + double-click" users ---
        // This enables McpCad-Install.bat and simple "extract zip and run" flow for non-technical CAD users.
        if (args.Any(a => a.Equals("--all", StringComparison.OrdinalIgnoreCase) ||
                          a.Equals("--install-all", StringComparison.OrdinalIgnoreCase)))
        {
            foreach (var a in _agents) a.Selected = true;
            RunSelectedAgentsAndExit(serverPath);
            return;
        }

        if (args.Any(a => a.Equals("--recommended", StringComparison.OrdinalIgnoreCase) ||
                          a.Equals("--install-recommended", StringComparison.OrdinalIgnoreCase)))
        {
            // Sensible defaults for most CAD + AI users
            var recommended = new[] { "Claude", "Cursor", "Grok", "OpenCode", "CAD Skills" };
            foreach (var a in _agents)
                a.Selected = recommended.Contains(a.Name, StringComparer.OrdinalIgnoreCase);
            RunSelectedAgentsAndExit(serverPath);
            return;
        }

        // --agents "Claude,Cursor,VS Code"
        var agentsArg = args.FirstOrDefault(a => a.StartsWith("--agents", StringComparison.OrdinalIgnoreCase));
        if (agentsArg is not null)
        {
            var list = agentsArg.Contains('=') ? agentsArg.Split('=', 2)[1] : (args.Length > 1 ? args[1] : "");
            var wanted = list.Split(new[] { ',', ';', ' ' }, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
            foreach (var a in _agents)
                a.Selected = wanted.Any(w => string.Equals(w, a.Name, StringComparison.OrdinalIgnoreCase));
            RunSelectedAgentsAndExit(serverPath);
            return;
        }

        if (args.Any(a => a.Equals("--help", StringComparison.OrdinalIgnoreCase) || a.Equals("-h", StringComparison.OrdinalIgnoreCase)))
        {
            Console.WriteLine("mcp-cad Installer");
            Console.WriteLine("Usage:");
            Console.WriteLine("  McpCad.Installer.exe                 GUI wizard (default for double-click)");
            Console.WriteLine("  McpCad.Installer.exe --tui           Interactive TUI (keyboard navigation)");
            Console.WriteLine("  McpCad.Installer.exe --recommended   Install for common agents (Claude, Cursor, Grok, OpenCode + CAD Skills)");
            Console.WriteLine("  McpCad.Installer.exe --all           Enable for every supported agent");
            Console.WriteLine("  Backups can be toggled in the TUI (select 'Backups' item and press Space)");
            Console.WriteLine("  McpCad.Installer.exe --agents Claude,Cursor");
            return;
        }

        // --- GUI wizard default (no args / double-click). --tui falls through to Spectre TUI below. ---
        if (!args.Any(a => a.Equals("--tui", StringComparison.OrdinalIgnoreCase)))
        {
            HideConsoleWindow();
            ApplicationConfiguration.Initialize();
            Application.Run(new InstallerWizardForm(_agents, _state, serverPath));
            return;
        }

        // --- Interactive TUI (polished version with logo, auto-detect, Continue/Exit buttons) ---
        int totalItems = _agents.Length + 2;
        int continueIndex = _agents.Length;
        int exitIndex = _agents.Length + 1;

        bool inSelection = true;

        while (inSelection)
        {
            Console.Clear();
            RenderLogo();
            AnsiConsole.MarkupLine("[grey]MCP server installer — AI Agents for CAD (Mechanical + Electronic)[/]");
            AnsiConsole.MarkupLine("[grey]j/k or arrows: move  |  Space or Enter on agent: toggle  |  Enter on button: activate  |  q: quit[/]");

            if (!string.IsNullOrEmpty(serverPath))
            {
                AnsiConsole.MarkupLine($"[grey]Server:[/] [dim]{serverPath}[/]");
            }
            else
            {
                AnsiConsole.MarkupLine("[red]⚠ Server not found.[/] Make sure McpCad.Server.exe is next to this installer (or in the same folder you extracted).");
            }

            AnsiConsole.WriteLine();

            for (int i = 0; i < _agents.Length; i++)
            {
                var agent = _agents[i];
                var check = agent.Selected ? "[green][[x]][/]" : "[[ ]]";
                var cursor = i == _selectedIdx ? "[cyan]>[/]" : " ";
                var name = i == _selectedIdx ? $"[bold cyan]{agent.Name}[/]" : agent.Name;
                AnsiConsole.MarkupLine($"  {cursor} {check} {name,-12} [grey]{agent.Description}[/]");
            }

            // Bottom action buttons - very explicit for "dumb user" safety
            AnsiConsole.WriteLine();
            AnsiConsole.MarkupLine("[grey]What do you want to do?[/]");

            bool onContinue = _selectedIdx == continueIndex;
            bool onExit = _selectedIdx == exitIndex;

            // IMPORTANT: literal [ and ] must be escaped as [[ and ]] when inside markup strings
            string continueBtn = onContinue
                ? "[bold white on blue]> [[ Continue ]] (install all selected agents)[/]"
                : "  [[ Continue ]] (install all selected agents)";
            string exitBtn = onExit
                ? "[bold white on blue]> [[ Exit ]][/]"
                : "  [[ Exit ]]";

            AnsiConsole.MarkupLine(continueBtn);
            AnsiConsole.MarkupLine(exitBtn);

            AnsiConsole.WriteLine();
            AnsiConsole.MarkupLine("[dim]Tip: Select the AI tools you use (Claude Desktop, Cursor, etc.) then press Enter on each.[/]");
            if (!string.IsNullOrEmpty(_status))
                AnsiConsole.MarkupLine(_status);

            var key = Console.ReadKey(intercept: true);
            _status = "";
            switch (key.Key)
            {
                case ConsoleKey.J or ConsoleKey.DownArrow:
                    _selectedIdx = (_selectedIdx + 1) % totalItems;
                    break;
                case ConsoleKey.K or ConsoleKey.UpArrow:
                    _selectedIdx = (_selectedIdx - 1 + totalItems) % totalItems;
                    break;
                case ConsoleKey.Spacebar:
                    if (_selectedIdx < _agents.Length)
                    {
                        ToggleAgentSelection(_agents[_selectedIdx]);
                    }
                    break;
                case ConsoleKey.Enter:
                    if (_selectedIdx < _agents.Length)
                    {
                        ToggleAgentSelection(_agents[_selectedIdx]);
                    }
                    else if (_selectedIdx == continueIndex)
                    {
                        if (string.IsNullOrEmpty(serverPath))
                        {
                            _status = "[red]Server not found. Place McpCad.Server.exe next to this installer before continuing.[/]";
                        }
                        else
                        {
                            var selected = _agents.Where(a => a.Selected && a.Name != "Backups").ToArray();
                            if (selected.Length == 0)
                            {
                                _status = "[yellow]No agents selected. Move up and use Space to toggle some.[/]";
                            }
                            else
                            {
                                InstallSelected(selected);
                                inSelection = false;
                            }
                        }
                    }
                    else if (_selectedIdx == exitIndex)
                    {
                        return;
                    }
                    break;
                case ConsoleKey.Q or ConsoleKey.Escape:
                    return;
            }
        }
    }

    private static void RenderLogo()
    {
        foreach (var line in LogoLines)
        {
            if (line.Contains("MCP-CAD"))
            {
                AnsiConsole.MarkupLine($"[{ElectricOrange}]{line}[/]");
            }
            else
            {
                AnsiConsole.MarkupLine($"[grey]{line}[/]");
            }
        }
        AnsiConsole.WriteLine();
    }

    private static void ToggleAgentSelection(McpAgent agent)
    {
        if (agent.Name == "Backups")
        {
            _state.BackupsEnabled = !_state.BackupsEnabled;
            _state.Save(StatePath);
            agent.Selected = _state.BackupsEnabled;
            agent.Description = _state.BackupsEnabled
                ? "Enabled — press Space to disable (recommended for safety)"
                : "Disabled — press Space to enable (not recommended)";
            _status = _state.BackupsEnabled ? "[green]Backups enabled[/]" : "[yellow]Backups disabled[/]";
        }
        else
        {
            agent.Selected = !agent.Selected;
        }
    }

    private static void AutoDetectAgents(McpAgent[] agents)
    {
        foreach (var agent in agents)
        {
            if (string.IsNullOrEmpty(agent.ConfigPath))
                continue;

            var dir = Path.GetDirectoryName(agent.ConfigPath);
            bool agentPresent = !string.IsNullOrEmpty(dir) &&
                                (Directory.Exists(dir) || File.Exists(agent.ConfigPath));

            if (agentPresent)
            {
                agent.Selected = true;
            }
        }
    }

    private static void InstallSelected(McpAgent[] selected)
    {
        var results = new List<(string Name, bool Success, string Message)>();

        AnsiConsole.Status()
            .Spinner(Spinner.Known.Dots)
            .SpinnerStyle(new Style(foreground: Color.FromHex("#FF5F00")))
            .Start($"Configuring {selected.Length} agent(s)...", ctx =>
            {
                foreach (var agent in selected)
                {
                    ctx.Status($"Installing for {agent.Name}...");
                    try
                    {
                        var path = agent.Run?.Invoke(_state, agent) ?? "unknown";
                        _state.LastAgent = agent.Name;
                        results.Add((agent.Name, true, path));
                    }
                    catch (Exception ex)
                    {
                        results.Add((agent.Name, false, ex.Message));
                    }
                }
                _state.Save(StatePath);
            });

        ShowSuccessScreen(results);
    }

    private static void ShowSuccessScreen(List<(string Name, bool Success, string Message)> results)
    {
        Console.Clear();
        RenderLogo();

        AnsiConsole.Write(new Rule($"[{ElectricOrange}]✓ Installation Complete[/]").RuleStyle(ElectricOrange));

        var successCount = results.Count(r => r.Success);
        var failCount = results.Count - successCount;

        var summary = successCount > 0
            ? $"[green]✓ Successfully configured {successCount} agent(s) with the MCP-CAD server[/]"
            : "[red]Some configurations had issues[/]";

        AnsiConsole.MarkupLine(summary);
        AnsiConsole.WriteLine();

        var table = new Table()
            .Border(TableBorder.Rounded)
            .BorderColor(Color.FromHex("#FF5F00"))
            .AddColumn("Agent")
            .AddColumn("Status")
            .AddColumn("Details");

        foreach (var (name, success, msg) in results)
        {
            var status = success ? "[green]OK[/]" : "[red]FAIL[/]";
            table.AddRow(name, status, msg.Length > 60 ? msg[..60] + "..." : msg);
        }

        AnsiConsole.Write(table);
        AnsiConsole.WriteLine();

        if (failCount == 0)
        {
            AnsiConsole.MarkupLine("[grey]Next steps: Restart your AI agent(s) / TUI so the mcp-cad server is loaded.[/]");
            AnsiConsole.MarkupLine("[grey]The server will then be available for AI-driven mechanical and electronic CAD workflows.[/]");
        }

        AnsiConsole.WriteLine();
        AnsiConsole.MarkupLine($"[{ElectricOrange}]Press Enter to exit...[/]");

        // Wait specifically for Enter (or any key, but message says Enter)
        while (Console.ReadKey(intercept: true).Key != ConsoleKey.Enter)
        {
            // keep waiting for Enter
        }
    }

    private static void RunAgent(McpAgent agent)
    {
        // Legacy single-run kept for compatibility if needed elsewhere
        try
        {
            var path = agent.Run?.Invoke(_state, agent) ?? "unknown";
            _status = $"[green]✅ {agent.Name} configured[/]  [dim]({path})[/]";
            _state.LastAgent = agent.Name;
            _state.Save(StatePath);

            // After any successful registration, show friendly next steps once
            if (!_status.Contains("Next steps"))
            {
                _status += "\n[green]Great![/] Close & reopen your AI client. Your CAD app (Inventor or SolidWorks) must be running when you chat with the agent.";
            }
        }
        catch (Exception ex)
        {
            _status = $"[red]❌ {agent.Name} failed[/] — {ex.Message}";
        }
    }

    private static void RunSelectedAgentsAndExit(string serverPath)
    {
        Console.WriteLine("mcp-cad installer (non-interactive mode)");
        if (string.IsNullOrEmpty(serverPath))
        {
            Console.WriteLine("ERROR: Could not locate McpCad.Server.exe next to the installer.");
            Console.WriteLine("Extract the full portable package so McpCad.Server.exe and McpCad.Installer.exe are in the same folder.");
            Environment.ExitCode = 1;
            return;
        }

        Console.WriteLine($"Server: {serverPath}");
        Console.WriteLine();

        bool any = false;
        var failures = 0;
        foreach (var agent in _agents.Where(a => a.Selected && a.Name != "Backups"))
        {
            any = true;
            try
            {
                var path = agent.Run?.Invoke(_state, agent) ?? "unknown";
                Console.WriteLine($"✅ {agent.Name}: configured → {path}");
                _state.LastAgent = agent.Name;
            }
            catch (Exception ex)
            {
                failures++;
                Console.WriteLine($"❌ {agent.Name}: FAILED — {ex.Message}");
            }
        }

        _state.Save(StatePath);

        if (!any)
        {
            Console.WriteLine("No agents were selected. Use --recommended, --all or --agents ...");
            Environment.ExitCode = 1;
        }
        else if (failures > 0)
        {
            Environment.ExitCode = 1;
        }
        else
        {
            Console.WriteLine();
            Console.WriteLine("Done. Next steps:");
            Console.WriteLine("  1. Close completely and reopen the AI tool(s) you configured (Claude Desktop, Cursor, etc.).");
            Console.WriteLine("  2. Have your CAD application running (Inventor or SolidWorks).");
            Console.WriteLine("  3. In the chat, say something like: \"Create a new part and sketch a 50mm square.\"");
            Console.WriteLine();
            Console.WriteLine("The AI will now have direct access to your CAD modeling tools via mcp-cad.");
        }
    }

    [DllImport("kernel32.dll")]
    private static extern IntPtr GetConsoleWindow();

    [DllImport("user32.dll")]
    private static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    private const int SW_HIDE = 0;

    private static void HideConsoleWindow()
    {
        var hWnd = GetConsoleWindow();
        if (hWnd != IntPtr.Zero)
            ShowWindow(hWnd, SW_HIDE);
    }
}
