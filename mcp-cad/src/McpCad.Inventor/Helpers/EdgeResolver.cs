using McpCad.Core.Exceptions;

namespace McpCad.Inventor.Helpers;

/// <summary>
/// Resolves comma-separated edge indices (1-based) to an Inventor EdgeCollection.
/// Example: "1,3,5" → EdgeCollection with SurfaceBody.Edges[1], [3], [5].
/// </summary>
public static class EdgeResolver
{
    /// <summary>
    /// Resolve a comma-separated string of edge indices to an EdgeCollection.
    /// </summary>
    /// <param name="compDef">The ComponentDefinition containing the SurfaceBody with edges.</param>
    /// <param name="edges">Comma-separated 1-based edge indices, e.g. "1,3,5".</param>
    /// <returns>An EdgeCollection populated with the resolved edges.</returns>
    /// <exception cref="InventorComException">Thrown when an edge index is invalid.</exception>
    public static dynamic Resolve(dynamic compDef, string edges)
    {
        if (string.IsNullOrWhiteSpace(edges))
            throw new InventorComException("Edge indices cannot be empty. Provide comma-separated 1-based indices, e.g. '1,3,5'.");

        // Use dynamic to access SurfaceBody.Edges via COM late binding
        // (handles both PartComponentDefinition and AssemblyComponentDefinition)
        dynamic surfaceBody = compDef.SurfaceBodies.Item(1);
        dynamic edgeCollection = compDef.Application.TransientObjects.CreateEdgeCollection();

        var indices = edges.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        foreach (var idxStr in indices)
        {
            if (!int.TryParse(idxStr, out int idx))
                throw new InventorComException($"Invalid edge index '{idxStr.Trim()}'. Must be a number.");

            try
            {
                dynamic edge = surfaceBody.Edges.Item(idx);
                edgeCollection.Add(edge);
            }
            catch (Exception ex)
            {
                throw new InventorComException($"Edge index {idx} does not exist. The part has {surfaceBody.Edges.Count} edges.", ex);
            }
        }

        return edgeCollection;
    }
}