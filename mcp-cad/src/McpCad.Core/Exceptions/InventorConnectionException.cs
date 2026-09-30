namespace McpCad.Core.Exceptions;

/// <summary>
/// Thrown when connection to Inventor fails or is not established.
/// </summary>
public class InventorConnectionException : Exception
{
    public InventorConnectionException(string message) : base(message) { }

    public InventorConnectionException(string message, Exception inner)
        : base(message, inner) { }
}