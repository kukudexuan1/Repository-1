using McpCad.Core;
using McpCad.Core.Exceptions;
using ModelContextProtocol.Server;
using System.ComponentModel;

namespace McpCad.Tools;

/// <summary>
/// Skill tools — composed MCP operations that combine multiple atomic provider calls.
/// Skills are higher-level workflows (e.g., skill_revolve = sketch + circle + line + revolve).
/// Each method delegates to ICadProvider and catches COM exceptions,
/// returning standardized error dictionaries per the error contract (D7).
/// Tool method names use snake_case to match Python tool names (S5.1).
/// </summary>
[McpServerToolType]
public class SkillTools(IMechanicalCadProvider provider)
{
    // ── Drawing skills (8) ──────────────────────────────────────────────

    [McpServerTool, Description("Create or activate a sketch on a work plane.")]
    public Dictionary<string, object?> skill_sketch(string plane = "XY")
        => Catch(() => provider.SketchCreate(plane));

    [McpServerTool, Description("Draw a line. Modes: simple (start→end) or midpoint (centered line).")]
    public Dictionary<string, object?> skill_line(
        string mode = "simple",
        double start_x = 0.0, double start_y = 0.0,
        double end_x = 0.0, double end_y = 0.0,
        double mid_x = 0.0, double mid_y = 0.0)
    {
        return Catch(() =>
        {
            if (mode == "simple")
                return provider.SketchLine(start_x, start_y, end_x, end_y);

            if (mode == "midpoint")
            {
                // Midpoint line: compute opposite endpoint from center
                double oppX = 2.0 * mid_x - end_x;
                double oppY = 2.0 * mid_y - end_y;
                return provider.SketchLine(oppX, oppY, end_x, end_y);
            }

            return ToolHelpers.Error($"Unknown mode '{mode}'. Use 'simple' or 'midpoint'.");
        });
    }

    [McpServerTool, Description("Draw a circle. Modes: center (cx,cy,radius) or 3point (through 3 perimeter points).")]
    public Dictionary<string, object?> skill_circle(
        string mode = "center",
        double cx = 0.0, double cy = 0.0, double radius = 1.0,
        double x1 = 0.0, double y1 = 0.0,
        double x2 = 0.0, double y2 = 0.0,
        double x3 = 0.0, double y3 = 0.0)
    {
        return Catch(() =>
        {
            if (mode == "center")
                return provider.SketchCircle(cx, cy, radius);

            if (mode == "3point")
            {
                var (calcCx, calcCy, calcR) = CircleFromThreePoints(x1, y1, x2, y2, x3, y3);
                return provider.SketchCircle(calcCx, calcCy, calcR);
            }

            return ToolHelpers.Error($"Unknown mode '{mode}'. Use 'center' or '3point'.");
        });
    }

    [McpServerTool, Description("Draw an arc. Modes: center (cx,sy,ex), sweep (radius+angles), or 3point.")]
    public Dictionary<string, object?> skill_arc(
        string mode = "center",
        double cx = 0.0, double cy = 0.0,
        double sx = 1.0, double sy = 0.0,
        double ex = 0.0, double ey = 1.0,
        bool ccw = true,
        double radius = 1.0, double start_angle = 0.0, double sweep_angle = 90.0,
        double x1 = 0.0, double y1 = 0.0,
        double x_mid = 0.0, double y_mid = 0.0,
        double x_end = 0.0, double y_end = 0.0)
    {
        return Catch(() =>
        {
            if (mode == "center")
            {
                double r = Math.Sqrt((sx - cx) * (sx - cx) + (sy - cy) * (sy - cy));
                double saRad = Math.Atan2(sy - cy, sx - cx);
                double swRad = SweepBetween(cx, cy, sx, sy, ex, ey, ccw);
                return provider.SketchArc(cx, cy, r, saRad * 180.0 / Math.PI, (saRad + swRad) * 180.0 / Math.PI);
            }

            if (mode == "sweep")
            {
                return provider.SketchArc(cx, cy, radius, start_angle, start_angle + sweep_angle);
            }

            if (mode == "3point")
            {
                var (acx, acy, ar) = CircleFromThreePoints(x1, y1, x_mid, y_mid, x_end, y_end);
                double saRad = Math.Atan2(y1 - acy, x1 - acx);
                double eaRad = Math.Atan2(y_end - acy, x_end - acx);
                double maRad = Math.Atan2(y_mid - acy, x_mid - acx);
                // Ensure arc passes through midpoint
                if (eaRad <= saRad) eaRad += 2.0 * Math.PI;
                if (maRad <= saRad) maRad += 2.0 * Math.PI;
                if (maRad > eaRad) eaRad -= 2.0 * Math.PI;
                return provider.SketchArc(acx, acy, ar, saRad * 180.0 / Math.PI, eaRad * 180.0 / Math.PI);
            }

            return ToolHelpers.Error($"Unknown mode '{mode}'. Use 'center', 'sweep', or '3point'.");
        });
    }

    [McpServerTool, Description("Draw a rectangle. Modes: diagonal (two corners) or center (center+corner).")]
    public Dictionary<string, object?> skill_rect(
        string mode = "diagonal",
        double x1 = 0.0, double y1 = 0.0,
        double x2 = 10.0, double y2 = 10.0,
        double cx = 0.0, double cy = 0.0,
        double corner_x = 5.0, double corner_y = 5.0)
    {
        return Catch(() =>
        {
            if (mode == "diagonal")
                return provider.SketchRectangle(x1, y1, x2, y2);

            if (mode == "center")
            {
                double oppX = 2.0 * cx - corner_x;
                double oppY = 2.0 * cy - corner_y;
                return provider.SketchRectangle(corner_x, corner_y, oppX, oppY);
            }

            return ToolHelpers.Error($"Unknown mode '{mode}'. Use 'diagonal' or 'center'.");
        });
    }

    [McpServerTool, Description("Draw a point.")]
    public Dictionary<string, object?> skill_point(double x = 0.0, double y = 0.0)
        => Catch(() => provider.SketchPoint(x, y));

    [McpServerTool, Description("Draw an ellipse. Center (cx,cy), major and minor radii, optional angle.")]
    public Dictionary<string, object?> skill_ellipse(
        double cx = 0.0, double cy = 0.0,
        double major_radius = 5.0, double minor_radius = 3.0,
        double angle = 0.0)
        => Catch(() => provider.SketchEllipse(cx, cy, major_radius, minor_radius, angle));

    [McpServerTool, Description("Draw a spline through fit points. Points format: 'x1,y1,x2,y2,...'")]
    public Dictionary<string, object?> skill_spline(string points = "", string fit_method = "sweet")
    {
        return Catch(() =>
        {
            if (string.IsNullOrWhiteSpace(points))
                return ToolHelpers.Error("Need at least 3 points for a spline.");
            return provider.SketchSpline(points, fit_method);
        });
    }

    // ── Pattern skills (2) ───────────────────────────────────────────────

    [McpServerTool, Description("Circular pattern of sketch entities around an axis point.")]
    public Dictionary<string, object?> skill_pattern_circular(
        string entities = "1", string axis = "1", int count = 6,
        double angle = 360.0, bool fitted = true, bool symmetric = false)
        => Catch(() => provider.SketchCircularPattern(entities, axis, count, angle, fitted, symmetric));

    [McpServerTool, Description("Rectangular pattern of sketch entities.")]
    public Dictionary<string, object?> skill_pattern_rectangular(
        string entities = "1", string x_axis = "1", int x_count = 2, double x_spacing = 5.0,
        string y_axis = "", int y_count = 1, double y_spacing = 0.0)
        => Catch(() => provider.SketchRectangularPattern(entities, x_axis, x_count, x_spacing, y_axis, y_count, y_spacing));

    // ── Modify skills (6) ───────────────────────────────────────────────

    [McpServerTool, Description("Move sketch entities by a vector (cm).")]
    public Dictionary<string, object?> skill_move(string entities = "1", double dx = 0.0, double dy = 0.0, bool copy = false)
        => Catch(() => provider.SketchMove(entities, dx, dy, copy));

    [McpServerTool, Description("Rotate sketch entities around a center point (degrees).")]
    public Dictionary<string, object?> skill_rotate(string entities = "1", double cx = 0.0, double cy = 0.0, double angle = 90.0, bool copy = false)
        => Catch(() => provider.SketchRotate(entities, cx, cy, angle, copy));

    [McpServerTool, Description("Scale sketch entities around a center point.")]
    public Dictionary<string, object?> skill_scale(string entities = "1", double cx = 0.0, double cy = 0.0, double factor = 2.0)
        => Catch(() => provider.SketchScale(entities, cx, cy, factor));

    [McpServerTool, Description("Offset sketch entities through a point (cm).")]
    public Dictionary<string, object?> skill_offset(string entities = "1", double offset_x = 0.0, double offset_y = 1.0, bool include_connected = false)
        => Catch(() => provider.SketchOffset(entities, offset_x, offset_y, include_connected));

    [McpServerTool, Description("Mirror sketch entities across a mirror line.")]
    public Dictionary<string, object?> skill_mirror(string entities = "1", string mirror_entity = "2")
        => Catch(() => provider.SketchMirror(entities, mirror_entity));

    [McpServerTool, Description("Trim a sketch entity to its intersection with another.")]
    public Dictionary<string, object?> skill_trim(string entity = "1", string cutting_entity = "2", string side = "end")
        => Catch(() => provider.SketchTrim(entity, cutting_entity, side));

    // ── Constraint + dimension skills (2) ────────────────────────────────

    [McpServerTool, Description("Add a geometric constraint. Modes: coincident, collinear, concentric, parallel, perpendicular, tangent, horizontal, vertical, equal, midpoint, symmetric, smooth.")]
    public Dictionary<string, object?> skill_constraint(
        string mode = "parallel", string entity1 = "1", string entity2 = "",
        string sym_line = "", string axis = "major")
        => Catch(() => provider.SketchConstraint(mode, entity1, entity2, sym_line, axis));

    [McpServerTool, Description("Add a dimension constraint. Modes: linear, radius, diameter, angle.")]
    public Dictionary<string, object?> skill_dimension(
        string mode = "linear", string entity1 = "1", string entity2 = "",
        double? value = null, string orientation = "aligned",
        double? position_x = null, double? position_y = null)
        => Catch(() => provider.SketchDimension(mode, entity1, entity2, value, orientation, position_x, position_y));

    // ── 3D skills (2) ───────────────────────────────────────────────────

    [McpServerTool, Description("Extrude a sketch profile. Auto-defaults to profile=1. Use profile=\"2,4\" for multi-region extrusion.")]
    public Dictionary<string, object?> skill_extrude(
        double distance,
        string direction = "positive",
        double taper = 0.0,
        string operation = "new_body",
        string profile = "1")
        => Catch(() => provider.Extrude(profile, distance, direction, taper, operation));

    [McpServerTool, Description("Revolve a profile around an axis. Auto-draws circle + axis if no profile provided.")]
    public Dictionary<string, object?> skill_revolve(
        string plane = "XY",
        string profile = "",
        double profile_cx = 3.0, double profile_cy = 0.0, double profile_radius = 1.0,
        double axis_x = 0.0, double axis_y1 = -1.0, double axis_y2 = 5.0,
        double angle = 360.0, string operation = "join")
    {
        var results = new Dictionary<string, object?>();

        try
        {
            // 1. Create sketch only when auto-drawing the profile
            if (string.IsNullOrEmpty(profile))
            {
                var sketchResult = provider.SketchCreate(plane);
                results["sketch"] = sketchResult;
                if (sketchResult.TryGetValue("success", out var ok) && ok is bool b && !b)
                    return results;
            }

            // 2. Draw profile if none provided
            string profileIndex = profile;
            if (string.IsNullOrEmpty(profile))
            {
                var profileResult = provider.SketchCircle(profile_cx, profile_cy, profile_radius);
                results["profile"] = profileResult;
                if (profileResult.TryGetValue("success", out var ok2) && ok2 is bool b2 && !b2)
                    return results;
                profileIndex = "1"; // first entity is the circle
            }

            // 3. Draw axis line (vertical at axis_x), tagged as "eje"
            var axisResult = provider.SketchLine(axis_x, axis_y1, axis_x, axis_y2, tag: "eje");
            results["axis"] = axisResult;
            if (axisResult.TryGetValue("success", out var ok3) && ok3 is bool b3 && !b3)
                return results;

            // 4. Revolve using tag reference
            var revolveResult = provider.Revolve(profileIndex, "@eje", angle, operation: operation);
            results["revolve"] = revolveResult;

            return results;
        }
        catch (InventorConnectionException ex)
        {
            return ToolHelpers.Error(ex.Message);
        }
        catch (InventorComException ex)
        {
            return ToolHelpers.Error(ex.Message);
        }
        catch (Exception ex)
        {
            return ToolHelpers.Error($"Unexpected error: {ex.Message}");
        }
    }

    // ── Sweep skill ──────────────────────────────────────────────────────

    [McpServerTool, Description("Sweep a profile along connected sketch entities. Use after creating both a profile sketch and a path sketch.")]
    public Dictionary<string, object?> skill_sweep(
        string profile, string path,
        string sweep_type = "path", string operation = "new_body",
        double taper = 0, string path_sketch = "", string profile_sketch = "")
        => Catch(() => provider.Sweep(profile, path, sweep_type, operation, taper, path_sketch, profile_sketch));

    // ── Delete sketch skill (1) ─────────────────────────────────────────

    [McpServerTool, Description("Delete the active sketch (must not be used by a feature).")]
    public Dictionary<string, object?> skill_delete_sketch()
        => Catch(provider.SketchDelete);

    // ── Helpers ──────────────────────────────────────────────────────────

    /// <summary>
    /// Compute center (cx, cy) and radius from three perimeter points
    /// using perpendicular bisector intersection.
    /// </summary>
    private static (double cx, double cy, double radius) CircleFromThreePoints(
        double x1, double y1, double x2, double y2, double x3, double y3)
    {
        double mx1 = (x1 + x2) / 2.0;
        double my1 = (y1 + y2) / 2.0;
        double mx2 = (x2 + x3) / 2.0;
        double my2 = (y2 + y3) / 2.0;

        double dx1 = x2 - x1;
        double dy1 = y2 - y1;
        double dx2 = x3 - x2;
        double dy2 = y3 - y2;

        const double eps = 1e-12;
        double ccx, ccy;

        if (Math.Abs(dy1) < eps)
        {
            if (Math.Abs(dy2) < eps)
                throw new ArgumentException("Points are collinear — cannot form a circle");
            double s2 = -dx2 / dy2;
            ccx = mx1;
            ccy = s2 * (ccx - mx2) + my2;
        }
        else if (Math.Abs(dy2) < eps)
        {
            double s1 = -dx1 / dy1;
            ccx = mx2;
            ccy = s1 * (ccx - mx1) + my1;
        }
        else
        {
            double s1 = -dx1 / dy1;
            double s2 = -dx2 / dy2;

            if (Math.Abs(s1 - s2) < eps)
                throw new ArgumentException("Points are collinear — cannot form a circle");

            ccx = (my2 - my1 + s1 * mx1 - s2 * mx2) / (s1 - s2);
            ccy = s1 * (ccx - mx1) + my1;
        }

        double r = Math.Sqrt((ccx - x1) * (ccx - x1) + (ccy - y1) * (ccy - y1));
        return (ccx, ccy, r);
    }

    /// <summary>
    /// Compute sweep angle in radians from start to end around center.
    /// </summary>
    private static double SweepBetween(double cx, double cy, double sx, double sy, double ex, double ey, bool ccw)
    {
        double aStart = Math.Atan2(sy - cy, sx - cx);
        double aEnd = Math.Atan2(ey - cy, ex - cx);

        if (ccw)
        {
            if (aEnd <= aStart)
                aEnd += 2.0 * Math.PI;
        }
        else
        {
            if (aEnd >= aStart)
                aEnd -= 2.0 * Math.PI;
        }

        return aEnd - aStart;
    }

    /// <summary>
    /// Error-catching helper matching AtomicTools pattern (D7).
    /// </summary>
    private static Dictionary<string, object?> Catch(Func<Dictionary<string, object?>> action)
    {
        try
        {
            return action();
        }
        catch (InventorConnectionException ex)
        {
            return ToolHelpers.Error(ex.Message);
        }
        catch (InventorComException ex)
        {
            return ToolHelpers.Error(ex.Message);
        }
        catch (Exception ex)
        {
            return ToolHelpers.Error($"Unexpected error: {ex.Message}");
        }
    }
}