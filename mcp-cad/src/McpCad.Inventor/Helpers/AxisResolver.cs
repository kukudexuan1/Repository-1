using McpCad.Core.Exceptions;

namespace McpCad.Inventor.Helpers;

/// <summary>
/// Resolves an axis reference for revolve operations.
/// Supports numeric indices and @tag references resolved through TagStore.
/// </summary>
public static class AxisResolver
{
    public static dynamic Resolve(dynamic sketch, string axisRef, int sketchIndex)
    {
        if (string.IsNullOrWhiteSpace(axisRef))
            throw new InventorComException("Axis reference cannot be empty.");

        // @tag resolution
        if (axisRef.StartsWith("@", StringComparison.OrdinalIgnoreCase))
        {
            string tag = axisRef[1..];
            var info = TagStore.ResolveWithType(sketchIndex, tag)
                ?? throw new InventorComException($"Tag '@{tag}' not found.");
            return info.type switch
            {
                TagStore.EntityType.SketchLine => sketch.SketchLines.Item(info.typeIdx),
                _ => throw new InventorComException($"Tag '@{tag}' is not a SketchLine.")
            };
        }

        // Numeric index — direct SketchLines lookup
        if (int.TryParse(axisRef, out int lineIdx))
        {
            try { return sketch.SketchLines.Item(lineIdx); }
            catch (Exception ex) { throw new InventorComException($"SketchLine {lineIdx} not found.", ex); }
        }

        throw new InventorComException($"Invalid axis reference '{axisRef}'.");
    }
}
