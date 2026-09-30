using System.Text.Json;
using System.Text.Json.Serialization;

namespace McpCad.Installer;

/// <summary>
/// Persisted state for the TUI installer.
/// Remembers user selections across runs: last-run agent, custom paths.
/// Ported from scripts/tui/state.py.
/// </summary>
public class State
{
    public string LastAgent { get; set; } = "";
    public Dictionary<string, string> CustomPaths { get; set; } = new();
    public Dictionary<string, string> Preferences { get; set; } = new();

    public bool BackupsEnabled
    {
        get => !Preferences.TryGetValue("backups_enabled", out var v) || !v.Equals("false", StringComparison.OrdinalIgnoreCase);
        set => Preferences["backups_enabled"] = value ? "true" : "false";
    }

    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
    };

    public static State Load(string path)
    {
        try
        {
            if (!File.Exists(path)) return new();
            var json = File.ReadAllText(path);
            return JsonSerializer.Deserialize<State>(json, JsonOpts) ?? new();
        }
        catch { return new(); }
    }

    public void Save(string path)
    {
        var dir = Path.GetDirectoryName(path);
        if (dir is not null) Directory.CreateDirectory(dir);
        var tmp = path + ".tmp";
        var json = JsonSerializer.Serialize(this, JsonOpts);
        File.WriteAllText(tmp, json);
        File.Move(tmp, path, overwrite: true);
    }
}
