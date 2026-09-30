using McpCad.Core.Exceptions;

namespace McpCad.Inventor.Helpers;

/// <summary>
/// Resolves a closed profile from a sketch with timeout protection.
/// Tries AddForSolid first (with 5s timeout), falls back to AddForSurface,
/// then tries the auto-computed profile collection.
/// </summary>
public static class ProfileResolver
{
    /// <summary>
    /// Resolve a profile from the given sketch.
    /// Strategy: auto-computed → AddForSolid with timeout → AddForSurface → throw.
    /// </summary>
    /// <param name="sketch">The planar sketch to resolve a profile from.</param>
    /// <param name="cancellationToken">Optional cancellation token for timeout control.</param>
    /// <returns>The resolved Profile object.</returns>
    /// <exception cref="InventorComException">Thrown when no closed profile can be found.</exception>
    public static dynamic Resolve(dynamic sketch, CancellationToken cancellationToken = default)
    {
        dynamic profiles = sketch.Profiles;

        // 1. Try existing auto-computed profile
        if (profiles.Count > 0)
            return profiles.Item(1);

        // 2. AddForSolid with 5s timeout
        using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        cts.CancelAfter(TimeSpan.FromSeconds(5));

        try
        {
            Task.Run(() =>
            {
                try { profiles.AddForSolid(); }
                catch { /* Profile computation may fail silently */ }
            }, cts.Token).Wait(cts.Token);

            if (profiles.Count > 0)
                return profiles.Item(1);
        }
        catch (OperationCanceledException)
        {
            // Timeout — fall through to AddForSurface
        }

        // 3. Fallback: AddForSurface
        try
        {
            profiles.AddForSurface();
            if (profiles.Count > 0)
                return profiles.Item(1);
        }
        catch
        {
            // Surface profile also failed
        }

        // 4. One more try: check if profiles appeared after all attempts
        if (profiles.Count > 0)
            return profiles.Item(1);

        throw new InventorComException("No closed profile found. Ensure the sketch contains a closed region.");
    }
}