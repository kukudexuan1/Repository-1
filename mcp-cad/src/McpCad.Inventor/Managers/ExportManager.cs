using McpCad.Core.Exceptions;
using McpCad.Core.Models;
using InvApp = Inventor.Application;

namespace McpCad.Inventor.Managers;

/// <summary>
/// Manages Inventor export operations: STEP, STL, PDF, DXF.
/// Uses Document.SaveAs(saveCopyAs=true) which works reliably with the interop.
/// The TranslatorAddIn.SaveCopyAs approach fails via dynamic dispatch.
/// </summary>
public class ExportManager(InventorDriver driver)
{
    private InvApp App => driver.InventorApp;

    private dynamic ActiveDocument()
    {
        var doc = driver.ActiveDocument
            ?? throw new InventorComException("No active document. Open or create a document first.");
        return doc;
    }

    private Dictionary<string, object?> RunExport(dynamic doc, string path)
    {
        try
        {
            doc.SaveAs(path, true);
            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["path"] = path,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Export failed for '{path}': {ex.Message}", ex); }
    }

    public Dictionary<string, object?> ExportStep(string path, Dictionary<string, object?>? opts = null)
    {
        try { return RunExport(ActiveDocument(), path); }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to export STEP: {ex.Message}", ex); }
    }

    public Dictionary<string, object?> ExportStl(string path, Dictionary<string, object?>? opts = null)
    {
        try { return RunExport(ActiveDocument(), path); }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to export STL: {ex.Message}", ex); }
    }

    public Dictionary<string, object?> ExportPdf(string path, Dictionary<string, object?>? opts = null)
    {
        try { return RunExport(ActiveDocument(), path); }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to export PDF: {ex.Message}", ex); }
    }

    public Dictionary<string, object?> ExportDxf(string path, Dictionary<string, object?>? opts = null)
    {
        try { return RunExport(ActiveDocument(), path); }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to export DXF: {ex.Message}", ex); }
    }
}
