using System.Runtime.InteropServices;

namespace McpCad.Inventor.Helpers;

/// <summary>
/// COM interop utilities for working with Inventor's object model.
/// </summary>
public static class ComDispatchHelper
{
    /// <summary>
    /// Wraps a COM object to ensure IDispatch support for late-bound dynamic access.
    /// Replicates Python's win32com.client.Dispatch(ent) pattern:
    /// queries IDispatch via GetIDispatchForObject and returns a clean wrapper.
    ///
    /// This is necessary because some Inventor COM objects (like SketchEntity
    /// when added to ObjectCollection for OffsetSketchEntitiesUsingPoint) only
    /// expose IUnknown through the interop RCW, causing E_FAIL.
    /// </summary>
    public static dynamic WrapDispatch(dynamic obj)
    {
        if (obj == null) return null!;
        try
        {
            IntPtr dispatchPtr = Marshal.GetIDispatchForObject((object)obj);
            return Marshal.GetObjectForIUnknown(dispatchPtr);
        }
        catch
        {
            return obj; // Fall back to original if IDispatch not available
        }
    }
}
