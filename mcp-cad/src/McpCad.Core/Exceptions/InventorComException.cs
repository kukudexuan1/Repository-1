namespace McpCad.Core.Exceptions;

/// <summary>
/// Thrown for COM-specific errors during Inventor operations.
/// Carries the HRESULT for diagnostics.
/// </summary>
public class InventorComException : Exception
{
    /// <summary>The COM HRESULT error code, if available.</summary>
    public int ComHResult { get; }

    public InventorComException(string message) : base(message) { }

    public InventorComException(string message, int hresult)
        : base($"{message} (HRESULT: 0x{hresult:X8})")
    {
        ComHResult = hresult;
    }

    public InventorComException(string message, Exception inner)
        : base(message, inner) { }
}