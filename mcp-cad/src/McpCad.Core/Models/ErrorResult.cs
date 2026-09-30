namespace McpCad.Core.Models;

/// <summary>
/// Static helper to build standardized error result dictionaries.
/// Every ICadProvider method returns Dictionary&lt;string, object?&gt;,
/// and errors are always represented as { "success": false, "error": "..." }.
/// </summary>
public static class ErrorResult
{
    /// <summary>
    /// Create an error result dictionary.
    /// </summary>
    /// <param name="message">Human-readable error description.</param>
    /// <param name="details">Optional additional key-value pairs merged into the result.</param>
    /// <returns>A dictionary with success=false and the error message.</returns>
    public static Dictionary<string, object?> Create(string message, params (string key, object? value)[] details)
    {
        var result = new Dictionary<string, object?>
        {
            ["success"] = false,
            ["error"] = message,
        };

        foreach (var (key, value) in details)
        {
            result[key] = value;
        }

        return result;
    }

    /// <summary>
    /// Create an error result from an exception.
    /// </summary>
    public static Dictionary<string, object?> FromException(Exception ex)
    {
        return Create(ex.Message, ("exception_type", ex.GetType().Name));
    }
}