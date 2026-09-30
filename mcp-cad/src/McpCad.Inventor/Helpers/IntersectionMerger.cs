using Inventor;

namespace McpCad.Inventor.Helpers;

/// <summary>
/// Merges sketch points at all intersection points between sketch curves.
/// Inventor's API doesn't auto-split regions when curves cross — the UI does,
/// but AddForSolid ignores intersections without merged points.
///
/// Approach: for each intersection:
/// 1. Create point P1 and constrain it to curve A (AddCoincident)
/// 2. Create point P2 and constrain it to curve B
/// 3. Merge P1 and P2 → resulting point is on both curves, splitting both
/// </summary>
public static class IntersectionMerger
{
    public static void MergeAll(dynamic sketch, Application app)
    {
        try
        {
            var gc = sketch.GeometricConstraints;

            // Collect all curves with their COM entity references
            var curves = new List<(dynamic entity, dynamic curve2d)>();

            foreach (dynamic line in sketch.SketchLines)
            {
                try { curves.Add((line, line.Geometry)); } catch { }
            }
            foreach (dynamic circle in sketch.SketchCircles)
            {
                try { curves.Add((circle, circle.Geometry)); } catch { }
            }
            try
            {
                foreach (dynamic arc in sketch.SketchArcs)
                {
                    try { curves.Add((arc, arc.Geometry)); } catch { }
                }
            }
            catch { }
            try
            {
                foreach (dynamic spline in sketch.SketchSplines)
                {
                    try { curves.Add((spline, spline.Geometry)); } catch { }
                }
            }
            catch { }

            // For each pair of curves, find and merge intersections
            for (int i = 0; i < curves.Count; i++)
            {
                for (int j = i + 1; j < curves.Count; j++)
                {
                    try
                    {
                        dynamic curveA = curves[i].curve2d;
                        dynamic curveB = curves[j].curve2d;
                        dynamic entityA = curves[i].entity;
                        dynamic entityB = curves[j].entity;
                        double tolerance = 1e-6;

                        dynamic intersections = curveA.IntersectWithCurve(curveB, tolerance);
                        if (intersections == null) continue;

                        foreach (dynamic pt in intersections)
                        {
                            try
                            {
                                double x = (double)pt.X;
                                double y = (double)pt.Y;

                                dynamic tg = app.TransientGeometry;
                                dynamic point2d = tg.CreatePoint2d(x, y);

                                // Create point constrained to curve A
                                dynamic spA = sketch.SketchPoints.Add(point2d, false);
                                gc.AddCoincident(spA, entityA);

                                // Create point constrained to curve B
                                dynamic spB = sketch.SketchPoints.Add(point2d, false);
                                gc.AddCoincident(spB, entityB);

                                // Merge → point is now on both curves, splitting both
                                spA.Merge(spB);
                            }
                            catch { }
                        }
                    }
                    catch { }
                }
            }
        }
        catch { /* Best-effort */ }
    }
}
