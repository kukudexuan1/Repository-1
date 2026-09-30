namespace McpCad.Tools;

/// <summary>
/// Shared helpers for building standardized result dictionaries
/// across all MCP tool classes.
/// </summary>
public static class ToolHelpers
{
    /// <summary>
    /// Build an error result dictionary with success=false.
    /// Used by the tool layer (D7) to catch COM exceptions and
    /// return structured error responses.
    /// </summary>
    public static Dictionary<string, object?> Error(string message) => new()
    {
        ["success"] = false,
        ["error"] = message,
    };

    /// <summary>
    /// Build a success result dictionary, optionally merging
    /// extra key-value pairs from the provided dictionary.
    /// </summary>
    public static Dictionary<string, object?> Ok(Dictionary<string, object?>? extra = null)
    {
        var result = new Dictionary<string, object?> { ["success"] = true };
        if (extra is not null)
            foreach (var kv in extra)
                result[kv.Key] = kv.Value;
        return result;
    }
}