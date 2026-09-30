using System.Runtime.InteropServices;
using McpCad.Core.Exceptions;
using InvApp = Inventor.Application;

namespace McpCad.Inventor;

/// <summary>
/// Low-level driver for Inventor COM connection lifecycle.
/// Handles connecting, disconnecting, health checks, and stale reference detection.
/// </summary>
public class InventorDriver
{
    private InvApp? _invApp;
    private bool _connected;

    // P/Invoke — .NET 8 doesn't expose Marshal.GetActiveObject
    [DllImport("ole32.dll")]
    private static extern int CLSIDFromProgID([MarshalAs(UnmanagedType.LPWStr)] string lpszProgID, out Guid lpclsid);

    [DllImport("oleaut32.dll")]
    private static extern int GetActiveObject(ref Guid rclsid, IntPtr pvReserved, [MarshalAs(UnmanagedType.IUnknown)] out object ppunk);

    private static object GetActiveComObject(string progId)
    {
        int hr = CLSIDFromProgID(progId, out Guid clsid);
        if (hr < 0)
            throw new COMException($"Invalid ProgID '{progId}'", hr);
        hr = GetActiveObject(ref clsid, IntPtr.Zero, out object obj);
        if (hr < 0)
            throw new COMException($"No running instance of '{progId}'", hr);
        return obj;
    }

    /// <summary>
    /// The active Inventor Application COM object.
    /// Auto-connects on first access if not already connected.
    /// Throws <see cref="InventorConnectionException"/> if connection fails.
    /// </summary>
    public InvApp InventorApp
    {
        get
        {
            if (_invApp is not null)
                return _invApp;

            // Auto-connect on first use — Connect() is idempotent and handles all error cases
            Connect();

            return _invApp ?? throw new InventorConnectionException(
                "Not connected to Inventor. Make sure Inventor is running.");
        }
    }

    /// <summary>Whether the driver currently holds a COM reference to Inventor.</summary>
    public bool IsConnected => _connected && _invApp is not null;

    /// <summary>
    /// Connect to a running Inventor instance via COM.
    /// Idempotent — returns existing connection if healthy.
    /// </summary>
    public Dictionary<string, object?> Connect()
    {
        // If already connected, probe health to detect stale references
        if (_connected && _invApp is not null)
        {
            var health = Health();
            if (health.TryGetValue("connected", out var conn) && conn is true)
                return health;
        }

        try
        {
            _invApp = (InvApp)GetActiveComObject("Inventor.Application");
            _connected = true;

            string version;
            try
            {
                version = _invApp.SoftwareVersion?.DisplayName ?? "unknown";
            }
            catch
            {
                version = "unknown";
            }

            return new Dictionary<string, object?>
            {
                ["connected"] = true,
                ["version"] = version,
            };
        }
        catch (COMException ex) when (ex.ErrorCode == unchecked((int)0x80040154))
        {
            // REGDB_E_CLASSNOTREG — Inventor not installed or not registered
            _invApp = null;
            _connected = false;
            return new Dictionary<string, object?>
            {
                ["connected"] = false,
                ["error"] = "Inventor is not installed or COM class not registered.",
            };
        }
        catch (COMException ex) when (ex.ErrorCode == unchecked((int)0x80080005))
        {
            // CO_E_SERVERFAILURE — Inventor running but access denied
            _invApp = null;
            _connected = false;
            return new Dictionary<string, object?>
            {
                ["connected"] = false,
                ["error"] = $"Permission denied accessing Inventor: {ex.Message}",
            };
        }
        catch (Exception ex)
        {
            _invApp = null;
            _connected = false;
            return new Dictionary<string, object?>
            {
                ["connected"] = false,
                ["error"] = $"Failed to connect to Inventor: {ex.Message}",
            };
        }
    }

    /// <summary>
    /// Release the COM reference to Inventor without closing the application.
    /// Idempotent — safe to call when not connected.
    /// </summary>
    public Dictionary<string, object?> Disconnect()
    {
        if (_invApp is not null)
        {
            try
            {
                Marshal.ReleaseComObject(_invApp);
            }
            catch
            {
                // Best-effort release — COM object may already be gone
            }
            _invApp = null;
        }
        _connected = false;
        return new Dictionary<string, object?> { ["status"] = "disconnected" };
    }

    /// <summary>
    /// Check connection health and document state.
    /// Always safe to call — never throws.
    /// </summary>
    public Dictionary<string, object?> Health()
    {
        if (_invApp is null || !_connected)
        {
            return DisconnectedHealth();
        }

        try
        {
            string version;
            try
            {
                version = _invApp.SoftwareVersion?.DisplayName ?? "unknown";
            }
            catch
            {
                version = "unknown";
            }

            int docsCount;
            try
            {
                docsCount = _invApp.Documents?.Count ?? 0;
            }
            catch
            {
                docsCount = 0;
            }

            string? activeDoc = null;
            try
            {
                dynamic? doc = _invApp.ActiveDocument;
                if (doc is not null)
                {
                    activeDoc = doc.FullFileName as string;
                    if (string.IsNullOrEmpty(activeDoc))
                        activeDoc = doc.DisplayName as string;
                }
            }
            catch
            {
                // No active document or COM reference is stale
            }

            return new Dictionary<string, object?>
            {
                ["connected"] = true,
                ["inventor_version"] = version,
                ["documents_open"] = docsCount,
                ["active_document"] = activeDoc,
            };
        }
        catch (COMException ex) when (ex.ErrorCode == unchecked((int)0x80010108))
        {
            // RPC_E_DISCONNECTED — Inventor was closed externally
            _invApp = null;
            _connected = false;
            return DisconnectedHealth();
        }
        catch
        {
            _invApp = null;
            _connected = false;
            return DisconnectedHealth();
        }
    }

    /// <summary>Get the active Inventor document, or null if none.</summary>
    public object? ActiveDocument
    {
        get
        {
            try { return InventorApp.ActiveDocument; }
            catch { return null; }
        }
    }

    /// <summary>
    /// Get the ComponentDefinition of the active document.
    /// Returns null if no document is active or on COM error.
    /// Uses dynamic as escape hatch for assembly vs part document differences.
    /// </summary>
    public dynamic? ComponentDefinition
    {
        get
        {
            try
            {
                var doc = ActiveDocument;
                if (doc is null) return null;
                // Use dynamic because PartDocument, AssemblyDocument etc.
                // have different ComponentDefinition types
                dynamic dynDoc = doc;
                return dynDoc.ComponentDefinition;
            }
            catch { return null; }
        }
    }

    private static Dictionary<string, object?> DisconnectedHealth() => new()
    {
        ["connected"] = false,
        ["inventor_version"] = null,
        ["documents_open"] = 0,
        ["active_document"] = null,
    };
}