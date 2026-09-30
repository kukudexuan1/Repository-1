using McpCad.Core.Exceptions;
using McpCad.Core.Models;
using InvApp = Inventor.Application;

namespace McpCad.Inventor.Managers;

/// <summary>
/// Manages Inventor document operations: open, create, save, close.
/// Uses InventorDriver for COM connection lifecycle.
/// Uses dynamic for COM calls that require DocumentTypeEnum — D3 escape hatch.
/// </summary>
public class DocumentManager(InventorDriver driver)
{
    // Inventor document-type COM constants (used via dynamic to bypass enum casting)
    private const int PartDocumentType = 12290;       // kPartDocumentObject
    private const int AssemblyDocumentType = 12291;   // kAssemblyDocumentObject
    // Drawing document type constant (for PDF export detection in ExportManager)
    internal const int DrawingDocumentType = 12293;  // kDrawingDocumentObject

    private InvApp App => driver.InventorApp;

    private dynamic ActiveDocument()
    {
        var doc = driver.ActiveDocument
            ?? throw new InventorComException("No active document. Open or create a document first.");
        return doc;
    }

    /// <summary>
    /// Open an existing Inventor document by file path.
    /// </summary>
    public Dictionary<string, object?> DocOpen(string path)
    {
        try
        {
            dynamic documents = App.Documents;
            dynamic doc = documents.Open(path);
            string fileName = (string?)doc.FullFileName ?? string.Empty;
            int docType = (int)doc.DocumentType;

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["document"] = fileName,
                ["document_type"] = docType,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to open document '{path}': {ex.Message}", ex); }
    }

    /// <summary>
    /// Create a new part document. Uses FileManager.GetTemplateFile when
    /// no template is specified.
    /// </summary>
    public Dictionary<string, object?> DocNewPart(string template = "")
    {
        try
        {
            dynamic fileManager = App.FileManager;
            string templatePath = string.IsNullOrWhiteSpace(template)
                ? (string)fileManager.GetTemplateFile(PartDocumentType)
                : template;

            dynamic documents = App.Documents;
            dynamic doc = documents.Add(PartDocumentType, templatePath, true);
            string fileName = (string?)doc.FullFileName ?? string.Empty;
            int docType = (int)doc.DocumentType;

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["document"] = fileName,
                ["document_type"] = docType,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to create part document: {ex.Message}", ex); }
    }

    /// <summary>
    /// Create a new assembly document.
    /// </summary>
    public Dictionary<string, object?> DocNewAssembly(string template = "")
    {
        try
        {
            dynamic fileManager = App.FileManager;
            string templatePath = string.IsNullOrWhiteSpace(template)
                ? (string)fileManager.GetTemplateFile(AssemblyDocumentType)
                : template;

            dynamic documents = App.Documents;
            dynamic doc = documents.Add(AssemblyDocumentType, templatePath, true);
            string fileName = (string?)doc.FullFileName ?? string.Empty;
            int docType = (int)doc.DocumentType;

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["document"] = fileName,
                ["document_type"] = docType,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to create assembly document: {ex.Message}", ex); }
    }

    /// <summary>
    /// Save the active document.
    /// </summary>
    public Dictionary<string, object?> DocSave()
    {
        try
        {
            var doc = ActiveDocument();
            doc.Save();
            string fileName = doc.FullFileName ?? string.Empty;

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["document"] = fileName,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to save document: {ex.Message}", ex); }
    }

    /// <summary>
    /// Save the active document to a new path.
    /// </summary>
    public Dictionary<string, object?> DocSaveAs(string path)
    {
        try
        {
            var doc = ActiveDocument();
            doc.SaveAs(path, true);
            string fileName = doc.FullFileName ?? string.Empty;

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["document"] = fileName,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to save document as '{path}': {ex.Message}", ex); }
    }

    /// <summary>
    /// Close the active document, optionally saving first.
    /// </summary>
    public Dictionary<string, object?> DocClose(bool save = true)
    {
        try
        {
            var doc = ActiveDocument();
            string fileName = doc.FullFileName ?? string.Empty;
            if (save)
                doc.Save();
            doc.Close();

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["document"] = fileName,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to close document: {ex.Message}", ex); }
    }
}