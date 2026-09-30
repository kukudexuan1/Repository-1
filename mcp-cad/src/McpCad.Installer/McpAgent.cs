using Tomlyn;
using Tomlyn.Model;

namespace McpCad.Installer;

public class McpAgent
{
    public string Name { get; init; } = "";
    public string Description { get; set; } = "";
    public bool Selected { get; set; } = true;
    public string? ConfigPath { get; init; }
    public string? SkillsPath { get; init; }
    public Func<State, McpAgent, string>? Run { get; init; }

    public string Label => Selected ? $"[[x]] {Name}" : $"[[ ]] {Name}";
}

public static class McpAgents
{
    public static McpAgent[] All(State state)
    {
        var serverPath = FindServerPath();

        var userProfile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        var appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);

        return new[]
        {
            new McpAgent
            {
                Name = "OpenCode",
                Description = FormatPathsDescription(
                    Path.Combine(userProfile, ".config", "opencode", "opencode.json"),
                    Path.Combine(userProfile, ".config", "opencode", "skills")),
                ConfigPath = Path.Combine(userProfile, ".config", "opencode", "opencode.json"),
                SkillsPath = Path.Combine(userProfile, ".config", "opencode", "skills"),
                Run = (s, a) =>
                {
                    var cfg = RegisterWithSchema(a.ConfigPath!, serverPath, "mcp", "local", a.Name, s);
                    var sk = TryInstallSkills(a.SkillsPath, a.Name, s);
                    return cfg + " | " + sk;
                },
            },
            new McpAgent
            {
                Name = "Claude",
                Description = FormatPathsDescription(
                    Path.Combine(appData, "Claude", "claude_desktop_config.json"),
                    Path.Combine(appData, "Claude", "skills")),
                ConfigPath = Path.Combine(appData, "Claude", "claude_desktop_config.json"),
                SkillsPath = Path.Combine(appData, "Claude", "skills"),
                Selected = false,
                Run = (s, a) =>
                {
                    var cfg = RegisterWithSchema(a.ConfigPath!, serverPath, "mcpServers", "stdio", a.Name, s);
                    var sk = TryInstallSkills(a.SkillsPath, a.Name, s);
                    return cfg + " | " + sk;
                },
            },
            new McpAgent
            {
                Name = "Pi",
                Description = FormatPathsDescription(
                    Path.Combine(userProfile, ".pi", "agent", "mcp.json"),
                    Path.Combine(userProfile, ".pi", "skills")),
                ConfigPath = Path.Combine(userProfile, ".pi", "agent", "mcp.json"),
                SkillsPath = Path.Combine(userProfile, ".pi", "skills"),
                Selected = false,
                Run = (s, a) =>
                {
                    var cfg = RegisterWithSchema(a.ConfigPath!, serverPath, "mcpServers", "stdio", a.Name, s);
                    var sk = TryInstallSkills(a.SkillsPath, a.Name, s);
                    return cfg + " | " + sk;
                },
            },
            new McpAgent
            {
                Name = "VS Code",
                Description = FormatPathsDescription(
                    Path.Combine(appData, "Code", "User", "mcp.json"),
                    Path.Combine(appData, "Code", "User", "skills")),
                ConfigPath = Path.Combine(appData, "Code", "User", "mcp.json"),
                SkillsPath = Path.Combine(appData, "Code", "User", "skills"),
                Selected = false,
                Run = (s, a) =>
                {
                    var cfg = RegisterWithSchema(a.ConfigPath!, serverPath, "servers", "stdio", a.Name, s);
                    var sk = TryInstallSkills(a.SkillsPath, a.Name, s);
                    return cfg + " | " + sk;
                },
            },
            new McpAgent
            {
                Name = "Cursor",
                Description = FormatPathsDescription(
                    Path.Combine(userProfile, ".cursor", "mcp.json"),
                    Path.Combine(userProfile, ".cursor", "skills")),
                ConfigPath = Path.Combine(userProfile, ".cursor", "mcp.json"),
                SkillsPath = Path.Combine(userProfile, ".cursor", "skills"),
                Selected = false,
                Run = (s, a) =>
                {
                    var cfg = RegisterWithSchema(a.ConfigPath!, serverPath, "mcpServers", "stdio", a.Name, s);
                    var sk = TryInstallSkills(a.SkillsPath, a.Name, s);
                    return cfg + " | " + sk;
                },
            },
            new McpAgent
            {
                Name = "Grok",
                Description = FormatPathsDescription(
                    Path.Combine(userProfile, ".grok", "config.toml"),
                    Path.Combine(userProfile, ".grok", "skills")),
                ConfigPath = Path.Combine(userProfile, ".grok", "config.toml"),
                SkillsPath = Path.Combine(userProfile, ".grok", "skills"),
                Selected = false,
                Run = (s, a) =>
                {
                    var cfg = RegisterGrok(a.ConfigPath!, serverPath, a.Name, s);
                    var sk = TryInstallSkills(a.SkillsPath, a.Name, s);
                    return cfg + " | " + sk;
                },
            },
            new McpAgent
            {
                Name = "CAD Skills",
                Description = "Install CAD skills to ALL supported agents' skills directories at once",
                Selected = true,
                Run = (s, a) => InstallSkillsToAllAgents(s),
            },
            new McpAgent
            {
                Name = "Backups",
                Description = state.BackupsEnabled 
                    ? "Enabled — press Space to disable (recommended for safety)" 
                    : "Disabled — press Space to enable (not recommended)",
                Selected = state.BackupsEnabled,
                Run = (s, a) =>
                {
                    return s.BackupsEnabled ? "Backups are enabled" : "Backups are disabled";
                },
            },
        };
    }

    /// <summary>
    /// Public helper so the UI can show the resolved server path to the user.
    /// </summary>
    public static string GetResolvedServerPath() => FindServerPath();

    /// <summary>
    /// Human-readable MCP + skills paths for GUI/TUI (uses ~ and %APPDATA% shorthands).
    /// </summary>
    public static string FormatPathsDescription(string? configPath, string? skillsPath)
    {
        var parts = new List<string>();
        if (!string.IsNullOrWhiteSpace(configPath))
            parts.Add($"MCP → {ToFriendlyPath(configPath)}");
        if (!string.IsNullOrWhiteSpace(skillsPath))
            parts.Add($"Skills → {ToFriendlyPath(skillsPath)}");
        return parts.Count > 0 ? string.Join("  |  ", parts) : "";
    }

    private static string ToFriendlyPath(string path)
    {
        var userProfile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        var appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);

        if (path.StartsWith(userProfile, StringComparison.OrdinalIgnoreCase))
            return "~" + path[userProfile.Length..].Replace('\\', '/');

        if (path.StartsWith(appData, StringComparison.OrdinalIgnoreCase))
            return "%APPDATA%" + path[appData.Length..].Replace('\\', '/');

        return path.Replace('\\', '/');
    }

    private static string FindServerPath()
    {
        var candidates = new List<string>();
        var baseDir = AppDomain.CurrentDomain.BaseDirectory?.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) ?? "";

        // 1. Most common for end-users: portable download — server files placed next to the Installer.exe
        candidates.Add(Path.Combine(baseDir, "McpCad.Server.exe"));

        // 2. Sensible subfolder layouts inside a zip/extracted package
        candidates.Add(Path.Combine(baseDir, "server", "McpCad.Server.exe"));
        candidates.Add(Path.Combine(baseDir, "mcp-cad", "McpCad.Server.exe"));
        candidates.Add(Path.Combine(baseDir, "bin", "McpCad.Server.exe"));

        // 3. Legacy dev build layout: walk upwards looking for dist/mcp-cad or dist/csharp-server-*
        var dir = baseDir;
        for (int i = 0; i < 8; i++)
        {
            var found = FindInDist(dir);
            if (found is not null)
                candidates.Add(found);

            // Also check if the scanned dir itself contains the exe directly (in case baseDir == the published folder)
            var directHere = Path.Combine(dir, "McpCad.Server.exe");
            if (File.Exists(directHere))
                candidates.Add(directHere);

            var parent = Path.GetDirectoryName(dir);
            if (parent is null || parent == dir) break;
            dir = parent;
        }

        // 4. CWD fallbacks (double-click scenarios sometimes have different CWD)
        var cwd = Environment.CurrentDirectory;
        candidates.Add(Path.Combine(cwd, "McpCad.Server.exe"));
        candidates.Add(Path.Combine(cwd, "dist", "mcp-cad", "McpCad.Server.exe"));

        // Pick the first that actually exists on disk
        foreach (var c in candidates.Distinct(StringComparer.OrdinalIgnoreCase))
        {
            if (!string.IsNullOrWhiteSpace(c) && File.Exists(c))
                return c;
        }

        return "";
    }

    private static string? FindInDist(string baseDir)
    {
        if (string.IsNullOrWhiteSpace(baseDir) || !Directory.Exists(baseDir))
            return null;

        var dist = Path.Combine(baseDir, "dist");
        if (!Directory.Exists(dist)) return null;

        // Prefer dist/mcp-cad/
        var direct = Path.Combine(dist, "mcp-cad", "McpCad.Server.exe");
        if (File.Exists(direct)) return direct;

        // Fallback: latest csharp-server-vN
        return Directory.GetDirectories(dist, "csharp-server-*")
            .Select(d => new { Path = d, Ver = ExtractVersion(d) })
            .Where(x => x.Ver >= 0)
            .OrderByDescending(x => x.Ver)
            .Select(x => Path.Combine(x.Path, "McpCad.Server.exe"))
            .FirstOrDefault(File.Exists);
    }

    private static int ExtractVersion(string dirPath)
    {
        var name = Path.GetFileName(dirPath);
        var idx = name.LastIndexOf('v');
        return idx >= 0 && int.TryParse(name[(idx + 1)..], out var v) ? v : -1;
    }

    private static void EnsureServerPath(string serverPath)
    {
        if (string.IsNullOrWhiteSpace(serverPath))
            throw new InvalidOperationException(
                "Could not locate McpCad.Server.exe next to the installer. " +
                "Extract the full portable package so McpCad.Server.exe and McpCad.Installer.exe are in the same folder.");
    }

    private static string RegisterWithSchema(string configPath, string serverPath, string parentKey, string type, string agentName, State? state = null)
    {
        EnsureServerPath(serverPath);

        // Backup config files before modifying (unless user disabled backups)
        var backupPath = BackupConfigFile(configPath, agentName, state);

        var config = ConfigManager.Read(configPath);
        var entry = type == "local"
            ? new Dictionary<string, object?> { ["type"] = "local", ["command"] = new[] { serverPath } }
            : new Dictionary<string, object?> { ["command"] = serverPath, ["args"] = Array.Empty<string>() };
        ConfigManager.MergeEntry(config, parentKey, new Dictionary<string, object?> { ["mcp-cad"] = entry });
        ConfigManager.Write(configPath, config);

        var result = configPath;
        if (backupPath is not null)
            result += $" [backup: {Path.GetFileName(backupPath)}]";
        return result;
    }

    private static string RegisterGrok(string configPath, string serverPath, string agentName, State? state = null)
    {
        EnsureServerPath(serverPath);

        // Backup config files before modifying (unless user disabled backups)
        var backupPath = BackupConfigFile(configPath, agentName, state);

        var dir = Path.GetDirectoryName(configPath);
        if (dir is not null) Directory.CreateDirectory(dir);

        TomlTable root;
        if (File.Exists(configPath))
        {
            var text = File.ReadAllText(configPath);
            try
            {
                root = Toml.ToModel(text) ?? new TomlTable();
            }
            catch
            {
                root = new TomlTable();
            }
        }
        else
        {
            root = new TomlTable();
        }

        TomlTable mcpServers;
        if (root.TryGetValue("mcp_servers", out var existing) && existing is TomlTable existingTable)
        {
            mcpServers = existingTable;
        }
        else
        {
            mcpServers = new TomlTable();
            root["mcp_servers"] = mcpServers;
        }

        var entry = new TomlTable
        {
            ["command"] = serverPath,
            ["args"] = new TomlArray(),
            ["enabled"] = true
        };
        mcpServers["mcp-cad"] = entry;

        var newToml = Toml.FromModel(root);

        // Tomlyn model serializer drops empty arrays. Ensure "args = []" is present for Grok.
        // The mcp-cad table is small, so we inject explicitly after its command line.
        if (!newToml.Contains("args"))
        {
            // Insert args = [] after the command line inside the mcp-cad table
            newToml = System.Text.RegularExpressions.Regex.Replace(
                newToml,
                @"(\[mcp_servers\.mcp-cad\][^\[]*?command\s*=\s*""[^""]*"")(\r?\n)",
                "$1\r\nargs = []\r\n",
                System.Text.RegularExpressions.RegexOptions.Singleline);
        }

        var tmp = configPath + ".tmp";
        File.WriteAllText(tmp, newToml.TrimEnd() + Environment.NewLine);
        File.Move(tmp, configPath, overwrite: true);

        var result = configPath;
        if (backupPath is not null)
            result += $" [backup: {Path.GetFileName(backupPath)}]";
        return result;
    }

    // ============================================================
    // CAD Skills installation — now for ALL supported agents
    // Each agent has its own SkillsPath (e.g. ~/.grok/skills, ~/.cursor/skills, etc.).
    // When you select an agent we register the MCP server AND copy the skills/
    // from the portable/repo into that agent's skills directory.
    // The "CAD Skills" item installs to every supported agent's skills dir at once.
    // ============================================================

    public static string InstallSkillsToAllAgents(State? state = null)
    {
        var userProfile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        var appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);

        // Map of (target skills dir, agent name for backup folder)
        var targets = new (string Path, string AgentName)[]
        {
            (Path.Combine(userProfile, ".config", "opencode", "skills"), "OpenCode"),
            (Path.Combine(appData, "Claude", "skills"), "Claude"),
            (Path.Combine(userProfile, ".pi", "skills"), "Pi"),
            (Path.Combine(appData, "Code", "User", "skills"), "VS Code"),
            (Path.Combine(userProfile, ".cursor", "skills"), "Cursor"),
            (Path.Combine(userProfile, ".grok", "skills"), "Grok"),
        };

        var results = new List<string>();
        foreach (var (path, agentName) in targets.Distinct())
        {
            try
            {
                results.Add(InstallSkills(path, agentName, state));
            }
            catch (Exception ex)
            {
                results.Add($"Skipped {agentName}: {ex.Message}");
            }
        }
        return string.Join(" ; ", results);
    }

    private static string TryInstallSkills(string? targetDir, string agentName, State? state = null)
    {
        if (string.IsNullOrWhiteSpace(targetDir))
            return "Skills: no target dir for this agent";
        try
        {
            return InstallSkills(targetDir, agentName, state);
        }
        catch (Exception ex)
        {
            return $"Skills skipped: {ex.Message}";
        }
    }

    private static string InstallSkills(string targetBaseDir, string agentName, State? state = null)
    {
        if (string.IsNullOrWhiteSpace(targetBaseDir))
            throw new ArgumentException("Target skills directory is required");

        var sourceDir = FindSkillsDir();
        if (string.IsNullOrWhiteSpace(sourceDir) || !Directory.Exists(sourceDir))
            throw new Exception("Could not locate 'skills/' folder (run from the full portable package or repo root).");

        var hasSkill = Directory.GetDirectories(sourceDir)
            .Any(d => File.Exists(Path.Combine(d, "SKILL.md")));
        if (!hasSkill)
            throw new Exception("Found 'skills/' but no SKILL.md subfolders.");

        Directory.CreateDirectory(targetBaseDir);

        int installed = 0;
        int backedUp = 0;
        foreach (var skillDir in Directory.GetDirectories(sourceDir))
        {
            if (!File.Exists(Path.Combine(skillDir, "SKILL.md")))
                continue;

            var skillName = Path.GetFileName(skillDir);
            var targetDir = Path.Combine(targetBaseDir, skillName);

            // Quirúrgico: only backup if the skill already exists in the target
            var backupPath = BackupExistingSkill(targetDir, agentName, state);
            if (backupPath is not null)
                backedUp++;

            CopyDirectory(skillDir, targetDir, overwrite: true);
            installed++;
        }

        var msg = $"CAD skills installed/updated ({installed}) → {targetBaseDir}";
        if (backedUp > 0)
            msg += $" [{backedUp} existing skill(s) backed up to ~/.mcp-cad/backups/skills/]";
        return msg;
    }

    private static string FindSkillsDir()
    {
        var baseDir = AppDomain.CurrentDomain.BaseDirectory?.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) ?? "";

        var candidates = new List<string>
        {
            Path.Combine(baseDir, "skills"),
            Path.Combine(baseDir, "mcp-cad", "skills"),
        };

        var dir = baseDir;
        for (int i = 0; i < 8; i++)
        {
            var candidate = Path.Combine(dir, "skills");
            if (Directory.Exists(candidate) &&
                Directory.GetDirectories(candidate).Any(d => File.Exists(Path.Combine(d, "SKILL.md"))))
                return candidate;

            var parent = Path.GetDirectoryName(dir);
            if (parent == null || parent == dir) break;
            dir = parent;
        }

        var cwdCandidate = Path.Combine(Environment.CurrentDirectory, "skills");
        if (Directory.Exists(cwdCandidate) &&
            Directory.GetDirectories(cwdCandidate).Any(d => File.Exists(Path.Combine(d, "SKILL.md"))))
            return cwdCandidate;

        return "";
    }

    private static void CopyDirectory(string sourceDir, string destDir, bool overwrite)
    {
        Directory.CreateDirectory(destDir);

        foreach (var file in Directory.GetFiles(sourceDir))
        {
            var destFile = Path.Combine(destDir, Path.GetFileName(file));
            File.Copy(file, destFile, overwrite);
        }

        foreach (var subDir in Directory.GetDirectories(sourceDir))
        {
            var destSubDir = Path.Combine(destDir, Path.GetFileName(subDir));
            CopyDirectory(subDir, destSubDir, overwrite);
        }
    }

    // ============================================================
    // Backups (quirúrgico / surgical approach)
    // - Config files: always backed up before modification (they are critical).
    // - Skills: only backed up if the target skill directory already exists.
    // Backups go to ~/.mcp-cad/backups/
    // ============================================================

    private static string GetBackupRoot()
    {
        return Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            ".mcp-cad", "backups");
    }

    private static string? BackupConfigFile(string originalPath, string agentName, State? state)
    {
        if (state != null && !state.BackupsEnabled)
            return null;

        if (string.IsNullOrWhiteSpace(originalPath) || !File.Exists(originalPath))
            return null;

        var backupDir = Path.Combine(GetBackupRoot(), "configs");
        Directory.CreateDirectory(backupDir);

        var timestamp = DateTime.Now.ToString("yyyy-MM-dd_HHmmss");
        var fileName = Path.GetFileName(originalPath);
        var backupPath = Path.Combine(backupDir, $"{timestamp}_{agentName}_{fileName}");

        File.Copy(originalPath, backupPath, overwrite: true);
        return backupPath;
    }

    private static string? BackupExistingSkill(string targetSkillDir, string agentName, State? state)
    {
        if (state != null && !state.BackupsEnabled)
            return null;

        if (string.IsNullOrWhiteSpace(targetSkillDir) || !Directory.Exists(targetSkillDir))
            return null;

        var backupRoot = Path.Combine(GetBackupRoot(), "skills", agentName.ToLowerInvariant());
        Directory.CreateDirectory(backupRoot);

        var timestamp = DateTime.Now.ToString("yyyy-MM-dd_HHmmss");
        var skillName = Path.GetFileName(targetSkillDir);
        var backupDir = Path.Combine(backupRoot, $"{timestamp}_{skillName}");

        CopyDirectory(targetSkillDir, backupDir, overwrite: true);
        return backupDir;
    }
}
