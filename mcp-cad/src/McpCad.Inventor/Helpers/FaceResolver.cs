using McpCad.Core.Exceptions;

namespace McpCad.Inventor.Helpers;

/// <summary>
/// Resolves comma-separated face indices (1-based) to an Inventor FaceCollection.
/// Example: "1,3,5" → FaceCollection with SurfaceBody.Faces[1], [3], [5].
/// Returns wrapped object for compatibility with both late-bound and early-bound APIs.
/// </summary>
public static class FaceResolver
{
    /// <summary>
    /// Resolve a comma-separated string of face indices to a wrapped FaceCollection.
    /// Each face is individually wrapped via ComDispatchHelper to ensure proper
    /// COM identity for early-bound APIs (Shell, Draft, Thicken).
    /// </summary>
    public static dynamic ResolveFaces(dynamic compDef, string faceIndices)
    {
        if (string.IsNullOrWhiteSpace(faceIndices))
            throw new InventorComException("Face indices cannot be empty. Provide comma-separated 1-based indices, e.g. '1,3,5'.");

        dynamic surfaceBody = compDef.SurfaceBodies.Item(1);
        dynamic faceCollection = compDef.Application.TransientObjects.CreateFaceCollection();

        var indices = faceIndices.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        foreach (var idxStr in indices)
        {
            if (!int.TryParse(idxStr, out int idx))
                throw new InventorComException($"Invalid face index '{idxStr.Trim()}'. Must be a number.");

            try
            {
                object rawFace = surfaceBody.Faces.Item(idx);
                dynamic face = ComDispatchHelper.WrapDispatch(rawFace);
                faceCollection.Add(face);
            }
            catch (Exception ex)
            {
                throw new InventorComException($"Face index {idx} does not exist. The part has {surfaceBody.Faces.Count} faces.", ex);
            }
        }

        return ComDispatchHelper.WrapDispatch(faceCollection);
    }
}
