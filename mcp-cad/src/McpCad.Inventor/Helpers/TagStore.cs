namespace McpCad.Inventor.Helpers;

/// <summary>
/// In-memory tag registry for sketch entities.
/// Stores the tag, entity type, and type-specific collection index
/// so resolvers can access entities directly without index mapping.
/// </summary>
public static class TagStore
{
    public enum EntityType { Unknown, SketchLine, SketchCircle, SketchArc, SketchPoint, SketchSpline, SketchEllipse }

    private readonly struct TagEntry
    {
        public string Tag { get; init; }
        public EntityType Type { get; init; }
        /// <summary>1-based index in the type-specific collection (e.g. SketchLines).</summary>
        public int TypeIndex { get; init; }
        /// <summary>1-based index in SketchEntities (global).</summary>
        public int EntityIndex { get; init; }
    }

    private static readonly Dictionary<(int sketchIdx, int entityIdx), TagEntry> _store = new();

    /// <summary>Associate a tag with a sketch entity.</summary>
    public static void SetTag(int sketchIdx, int entityIdx, string tag,
        EntityType type = EntityType.Unknown, int typeIndex = 0)
    {
        _store[(sketchIdx, entityIdx)] = new TagEntry
        {
            Tag = tag, Type = type, TypeIndex = typeIndex, EntityIndex = entityIdx
        };
    }

    /// <summary>Get the tag for a sketch entity, or null.</summary>
    public static string? GetTag(int sketchIdx, int entityIdx)
        => _store.TryGetValue((sketchIdx, entityIdx), out var e) ? e.Tag : null;

    /// <summary>Resolve a tag to its entity index, or null.</summary>
    public static int? Resolve(int sketchIdx, string tag)
    {
        foreach (var ((si, _), entry) in _store)
            if (si == sketchIdx && entry.Tag == tag) return entry.EntityIndex;
        return null;
    }

    /// <summary>Resolve a tag and return entity index, type, and type-specific index.</summary>
    public static (int entityIdx, EntityType type, int typeIdx)? ResolveWithType(int sketchIdx, string tag)
    {
        foreach (var ((si, _), entry) in _store)
            if (si == sketchIdx && entry.Tag == tag) return (entry.EntityIndex, entry.Type, entry.TypeIndex);
        return null;
    }

    public static void Clear() => _store.Clear();
}
