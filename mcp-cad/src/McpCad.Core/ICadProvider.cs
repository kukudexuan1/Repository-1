namespace McpCad.Core;

/// <summary>
/// Common provider interface for all CAD backends.
/// Implementations connect to a specific CAD application (Inventor, SolidWorks, KiCad…).
/// Domain-specific operations live in derived interfaces
/// (<see cref="IMechanicalCadProvider"/>, IElectronicCadProvider, etc.).
/// </summary>
public interface ICadProvider
{
    #region Connection

    Dictionary<string, object?> Connect();
    Dictionary<string, object?> Disconnect();
    Dictionary<string, object?> Health();

    #endregion

    #region Documents

    Dictionary<string, object?> DocOpen(string path);
    Dictionary<string, object?> DocNewPart(string template = "");
    Dictionary<string, object?> DocNewAssembly(string template = "");
    Dictionary<string, object?> DocSave();
    Dictionary<string, object?> DocSaveAs(string path);
    Dictionary<string, object?> DocClose(bool save = true);

    #endregion

    #region Export

    Dictionary<string, object?> ExportStep(string path, Dictionary<string, object?>? options = null);
    Dictionary<string, object?> ExportStl(string path, Dictionary<string, object?>? options = null);
    Dictionary<string, object?> ExportPdf(string path, Dictionary<string, object?>? options = null);
    Dictionary<string, object?> ExportDxf(string path, Dictionary<string, object?>? options = null);

    #endregion
}
