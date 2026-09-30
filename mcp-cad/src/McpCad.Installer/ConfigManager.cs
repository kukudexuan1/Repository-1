using System.Text.Json;

namespace McpCad.Installer;

/// <summary>
/// JSON config read/write/deep-merge for MCP agent registration.
/// Ported from scripts/tui/install_logic.py.
/// </summary>
public static class ConfigManager
{
    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        WriteIndented = true,
        PropertyNameCaseInsensitive = true,
    };

    public static Dictionary<string, object?> Read(string path)
    {
        try
        {
            if (!File.Exists(path)) return new();
            var json = File.ReadAllText(path);
            return JsonSerializer.Deserialize<Dictionary<string, object?>>(json, JsonOpts) ?? new();
        }
        catch { return new(); }
    }

    /// <summary>
    /// Deep merge a nested entry under parentKey (e.g. "mcpServers", "servers", "mcp").
    /// Preserves existing entries in the parent object.
    /// </summary>
    public static void MergeEntry(Dictionary<string, object?> config, string parentKey, object value)
    {
        if (config.TryGetValue(parentKey, out var existing) && existing is JsonElement je)
        {
            var existingDict = JsonSerializer.Deserialize<Dictionary<string, object?>>(je.GetRawText(), JsonOpts) ?? new();
            var newDict = JsonSerializer.Deserialize<Dictionary<string, object?>>(
                JsonSerializer.Serialize(value, JsonOpts), JsonOpts) ?? new();
            DeepMerge(existingDict, newDict);
            config[parentKey] = existingDict;
        }
        else if (existing is Dictionary<string, object?> existingObj)
        {
            var newDict = value as Dictionary<string, object?> ?? new();
            DeepMerge(existingObj, newDict);
        }
        else
        {
            config[parentKey] = value;
        }
    }

    private static void DeepMerge(Dictionary<string, object?> target, Dictionary<string, object?> source)
    {
        foreach (var (key, value) in source)
            target[key] = value;
    }

    public static void Write(string path, Dictionary<string, object?> config)
    {
        var dir = Path.GetDirectoryName(path);
        if (dir is not null) Directory.CreateDirectory(dir);
        var tmp = path + ".tmp";
        var json = JsonSerializer.Serialize(config, JsonOpts);
        File.WriteAllText(tmp, json);
        File.Move(tmp, path, overwrite: true);
    }
}
