using McpCad.Core.Exceptions;
using McpCad.Core.Models;
using McpCad.Inventor.Helpers;
using InvApp = Inventor.Application;

namespace McpCad.Inventor.Managers;

/// <summary>
/// Manages 2D sketch operations: create, draw, dimension, pattern, transform.
/// Tracks an active sketch so draw commands target the right object.
/// </summary>
public class SketchManager
{
    private readonly InventorDriver _driver;
    private dynamic? _activeSketch;
    private int _activeSketchIndex;
    private object? _lastEndpoint;
    private object? _firstStartpoint;

    // Work-plane indices in Inventor (1-based COM collection)
    private static readonly Dictionary<string, int> PlaneMap = new(StringComparer.OrdinalIgnoreCase)
    {
        ["XY"] = 1,
        ["XZ"] = 2,
        ["YZ"] = 3,
    };

    // Spline fit method enum values
    private static readonly Dictionary<string, int> SplineFitMethods = new(StringComparer.OrdinalIgnoreCase)
    {
        ["smooth"] = 26369,
        ["sweet"] = 26370,
        ["autocad"] = 26371,
    };

    // Dimension orientation enum values
    private static readonly Dictionary<string, int> DimensionOrientations = new(StringComparer.OrdinalIgnoreCase)
    {
        ["aligned"] = 19203,
        ["horizontal"] = 19201,
        ["vertical"] = 19202,
    };

    public SketchManager(InventorDriver driver) => _driver = driver;

    // ── Internal guards ───────────────────────────────────────────────

    private InvApp App => _driver.InventorApp;

    private dynamic EnsureActiveSketch()
    {
        if (_activeSketch is null)
            throw new InventorComException("No active sketch. Call SketchCreate() first.");
        return _activeSketch;
    }

    private dynamic TransientGeometry() => App.TransientGeometry;

    private dynamic ActiveDocument()
    {
        var doc = _driver.ActiveDocument
            ?? throw new InventorComException("No active document. Open or create a document first.");
        return doc;
    }

    private dynamic ComponentDefinition() => _driver.ComponentDefinition
        ?? throw new InventorComException("No component definition available.");

    private dynamic BuildEntityCollection(dynamic sketch, string entities)
    {
        var col = App.TransientObjects.CreateObjectCollection();
        foreach (var idxStr in entities.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            var ent = sketch.SketchEntities.Item(int.Parse(idxStr));
            col.Add(ent);
        }
        return col;
    }

    // ── Public API ────────────────────────────────────────────────────

    private static double[] ParseVector(string value)
    {
        return value.Trim('(', ')').Split(',', StringSplitOptions.TrimEntries)
            .Select(double.Parse).ToArray();
    }

    public Dictionary<string, object?> SketchCreate(string plane = "XY")
    {
        try
        {
            var compDef = ComponentDefinition();
            // Use dynamic dispatch — works for both PartComponentDefinition and AssemblyComponentDefinition
            dynamic dynCompDef = ComDispatchHelper.WrapDispatch(compDef);

            dynamic? workPlane = null;
            if (PlaneMap.TryGetValue(plane, out int planeIndex))
            {
                // Built-in origin plane (1=XY, 2=XZ, 3=YZ)
                workPlane = dynCompDef.WorkPlanes[planeIndex];
            }
            else
            {
                // A work plane created earlier via work_plane (e.g. an offset
                // plane whose auto name is like "工作平面1"): resolve it from the
                // WorkPlanes collection by name, then by numeric index. This makes
                // sketch_create(plane=<work_plane 返回的 name>) actually work, as the
                // tool docs promise (needed for keyway/hole tangent planes).
                try { workPlane = dynCompDef.WorkPlanes.Item(plane); }
                catch { workPlane = null; }
                if (workPlane is null && int.TryParse(plane, out int wpIdx) && wpIdx >= 1)
                {
                    try { workPlane = dynCompDef.WorkPlanes.Item(wpIdx); }
                    catch { workPlane = null; }
                }
            }

            if (workPlane is null)
                return ErrorResult.Create(
                    $"Invalid plane '{plane}'. Use 'XY', 'XZ', 'YZ', or the name returned by work_plane " +
                    "(e.g. an offset plane name like '工作平面1').");

            dynamic sketch = dynCompDef.Sketches.Add(workPlane);

            // ── Deterministic sketch orientation ──────────────────────────
            // Sketches.Add lets Inventor pick the sketch X/Y axes with its
            // internal default logic, which per the Inventor API docs is
            // "arbitrary alignment" derived from the parent geometry. That is
            // why an offset work plane (e.g. XY@Z=1.5 from work_plane) ends up
            // with a DIFFERENT u/v→model mapping than the origin XY plane, so a
            // keyway rectangle drawn in (u,v) lands rotated/across the shaft.
            // We pin the orientation to the world axes so the mapping is fixed
            // and predictable on every plane (origin OR offset):
            //   normal Z (XY-family) → u=+X, v=+Y
            //   normal Y (XZ-family) → u=+X, v=+Z
            //   normal X (YZ-family) → u=+Y, v=+Z
            // i.e. sketch-X = first world axis (X→Y→Z) that lies IN the plane.
            // IMPORTANT: the world axis is selected by its actual DIRECTION, not
            // by collection index — Inventor's WorkAxes/WorkPoints ordering is
            // NOT guaranteed to be X,Y,Z / origin-first, and indexing by 1/2/3
            // silently picked the wrong axis (locked u=+Y instead of +X, which
            // sent the revolve body down the Y axis).
            string? sketchXDir = null;
            string? sketchYDir = null;
            string? sketchOrigin = null;
            try
            {
                dynamic planeGeom = sketch.PlanarEntityGeometry; // Plane
                dynamic normal = planeGeom.Normal;               // UnitVector
                double nx = (double)normal.X, ny = (double)normal.Y, nz = (double)normal.Z;
                const double eps = 1e-6;

                // Desired sketch +X world direction: first of X,Y,Z that lies in
                // the plane (its component along the normal is ~0).
                double wantX = 0, wantY = 0, wantZ = 0;
                if (Math.Abs(nx) < eps) wantX = 1;          // world X in plane
                else if (Math.Abs(ny) < eps) wantY = 1;     // world Y in plane
                else if (Math.Abs(nz) < eps) wantZ = 1;     // world Z in plane

                if (wantX != 0 || wantY != 0 || wantZ != 0)
                {
                    // Pick the world work axis whose direction is (anti)parallel
                    // to the desired direction, reading real directions.
                    dynamic? chosenAxis = null;
                    bool natural = true;
                    int axCount = (int)dynCompDef.WorkAxes.Count;
                    for (int i = 1; i <= axCount; i++)
                    {
                        dynamic ax = dynCompDef.WorkAxes[i];
                        dynamic d;
                        try { d = ax.Line.Direction; } catch { continue; }
                        double dx = (double)d.X, dy = (double)d.Y, dz = (double)d.Z;
                        double dot = dx * wantX + dy * wantY + dz * wantZ;
                        if (Math.Abs(Math.Abs(dot) - 1.0) < 1e-3)
                        {
                            chosenAxis = ax;
                            natural = dot > 0; // ensure sketch +X points +want
                            break;
                        }
                    }

                    // Grounded origin work point (0,0,0), found by coordinate.
                    dynamic? originPt = null;
                    int wpCount = (int)dynCompDef.WorkPoints.Count;
                    for (int i = 1; i <= wpCount; i++)
                    {
                        dynamic wp = dynCompDef.WorkPoints[i];
                        dynamic p;
                        try { p = wp.Point; } catch { continue; }
                        if (Math.Abs((double)p.X) < eps && Math.Abs((double)p.Y) < eps && Math.Abs((double)p.Z) < eps)
                        {
                            originPt = wp;
                            break;
                        }
                    }

                    if (chosenAxis is not null && originPt is not null)
                    {
                        sketch.AxisEntity = chosenAxis;
                        sketch.AxisIsX = true;
                        sketch.NaturalAxisDirection = natural;
                        sketch.OriginPoint = originPt;

                        // Read back actual model-space +X (u) direction.
                        dynamic xdir = sketch.AxisEntityGeometry.Direction;
                        double ux = (double)xdir.X, uy = (double)xdir.Y, uz = (double)xdir.Z;
                        if (!natural) { ux = -ux; uy = -uy; uz = -uz; }
                        sketchXDir = $"({ux:0.###}, {uy:0.###}, {uz:0.###})";
                        // v = normal × u (right-handed), the sketch +Y direction.
                        double vx = ny * uz - nz * uy;
                        double vy = nz * ux - nx * uz;
                        double vz = nx * uy - ny * ux;
                        sketchYDir = $"({vx:0.###}, {vy:0.###}, {vz:0.###})";
                    }
                }

                // Sketch (0,0) in world space. Together with u,v this is the full
                // frame: world(P) = origin + x*u + y*v. Lets the caller SEE where
                // the sketch actually sits (e.g. an offset plane at Z=1.5 → origin
                // (0,0,1.5)) and self-correct instead of guessing.
                try
                {
                    dynamic o = sketch.OriginPointGeometry;
                    sketchOrigin = $"({(double)o.X:0.###}, {(double)o.Y:0.###}, {(double)o.Z:0.###})";
                }
                catch { sketchOrigin = null; }
            }
            catch
            {
                // If a plane/point cannot be oriented (unusual planes), keep the
                // default orientation rather than failing sketch creation.
                sketchXDir = null;
                sketchYDir = null;
            }

            if (sketchXDir is null || sketchYDir is null || sketchOrigin is null)
            {
                try { sketch.Delete(); } catch { }
                return ErrorResult.Create(
                    $"Could not establish a deterministic sketch frame on plane '{plane}'.");
            }

            _activeSketch = sketch;
            _activeSketchIndex = dynCompDef.Sketches.Count;
            // Fresh sketch => fresh polyline chain (prevents cross-sketch leakage).
            _lastEndpoint = null;
            _firstStartpoint = null;
            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["sketch_name"] = sketch.Name as string,
                ["plane"] = PlaneMap.ContainsKey(plane) ? plane.ToUpperInvariant() : plane,
                // Model-space directions of the sketch axes, e.g. "(1, 0, 0)".
                // Sketch input (x,y) maps to world: origin + x*u + y*v. Use these
                // to convert contract world coords → (x,y): x=(P-origin)·u,
                // y=(P-origin)·v. On a locked XY plane u=(1,0,0), v=(0,1,0).
                ["sketch_frame"] = new Dictionary<string, object?>
                {
                    ["origin"] = ParseVector(sketchOrigin),
                    ["u"] = ParseVector(sketchXDir),
                    ["v"] = ParseVector(sketchYDir),
                },
                ["sketch_x_model_dir"] = sketchXDir,
                ["sketch_y_model_dir"] = sketchYDir,
                // World coords of sketch (0,0). world(P)=origin + x*u + y*v.
                ["sketch_origin_model"] = sketchOrigin,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to create sketch on plane '{plane}'", ex); }
    }

    public Dictionary<string, object?> SketchLine(
        double x1, double y1, double x2, double y2,
        string? tag = null, bool connect = false, bool construction = false)
    {
        var sketch = EnsureActiveSketch();
        try
        {
            var tg = TransientGeometry();
            object start, end;

            // connect=true continues the current polyline from the previous
            // connected segment's endpoint. connect=false is a standalone line
            // that must NOT feed the chain state — otherwise a construction/axis
            // line drawn just before a profile would hijack the profile's first
            // segment start point (it would inherit the axis endpoint instead of
            // using its own x1,y1).
            bool chaining = connect && _lastEndpoint is not null;
            bool autoClosed = false;

            if (chaining)
            {
                start = _lastEndpoint!;
                // Auto-close: if this segment ends at the chain's first start
                // point, reuse that SketchPoint so the loop closes cleanly.
                if (_firstStartpoint is not null)
                {
                    double fpX = ((dynamic)_firstStartpoint).Geometry.X;
                    double fpY = ((dynamic)_firstStartpoint).Geometry.Y;
                    if (Math.Abs(x2 - fpX) < 0.001 && Math.Abs(y2 - fpY) < 0.001)
                    {
                        end = _firstStartpoint;
                        autoClosed = true;
                    }
                    else
                    {
                        end = tg.CreatePoint2d(x2, y2);
                    }
                }
                else
                {
                    end = tg.CreatePoint2d(x2, y2);
                }
            }
            else
            {
                start = tg.CreatePoint2d(x1, y1);
                end = tg.CreatePoint2d(x2, y2);
            }

            dynamic line = sketch.SketchLines.AddByTwoPoints(start, end);
            line.Construction = construction;

            if (!connect || autoClosed)
            {
                // Standalone line, or the chain just closed: break the chain so
                // it cannot leak into the next line.
                _lastEndpoint = null;
                _firstStartpoint = null;
            }
            else
            {
                // Starting or continuing a connected polyline.
                if (!chaining)
                    _firstStartpoint = line.StartSketchPoint;
                _lastEndpoint = line.EndSketchPoint;
            }

            if (!string.IsNullOrEmpty(tag))
            {
                int entityIdx = sketch.SketchEntities.Count;
                int typeIdx = sketch.SketchLines.Count;
                TagStore.SetTag(_activeSketchIndex, entityIdx, tag,
                    TagStore.EntityType.SketchLine, typeIdx);
            }

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["entity_type"] = "line",
                ["start"] = new[] { x1, y1 },
                ["end"] = new[] { x2, y2 },
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to draw line: {ex.Message}", ex); }
    }

    public Dictionary<string, object?> SketchLineClose()
    {
        var sketch = EnsureActiveSketch();
        try
        {
            if (_lastEndpoint is null || _firstStartpoint is null)
                return ErrorResult.Create("No open profile to close");

            dynamic line = sketch.SketchLines.AddByTwoPoints(_lastEndpoint, _firstStartpoint);
            _lastEndpoint = null;
            _firstStartpoint = null;
            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["entity_type"] = "line",
                ["operation"] = "close_profile",
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to close profile: {ex.Message}", ex); }
    }

    /// <summary>
    /// List all closed profiles in the active sketch with area and region info.
    /// Use this to identify which profile index to pass to extrude/revolve.
    /// </summary>
    public Dictionary<string, object?> SketchProfiles()
    {
        var sketch = EnsureActiveSketch();
        try
        {
            // Merge intersection points so crossing curves create sub-regions
            IntersectionMerger.MergeAll(sketch, App);

            dynamic profiles = sketch.Profiles;

            // Compute profiles fresh each time — we'll do destructive path deletion
            // to read individual region properties, then recreate.
            // First pass: create a profile and count paths.
            if (profiles.Count > 0)
            {
                // Clean up any existing profile before recomputing
                try { profiles.Item(1).Delete(); } catch { }
            }

            dynamic fullProfile = profiles.AddForSolid(false);

            // Count paths by iterating
            var pathCount = 0;
            try
            {
                foreach (dynamic _ in fullProfile)
                    pathCount++;
            }
            catch { }

            // Now for each path, create a temporary Profile with only that path,
            // read its RegionProperties, and clean up.
            var profileList = new List<Dictionary<string, object?>>();

            for (int i = 1; i <= pathCount; i++)
            {
                // Recreate the profile fresh
                // Clean up old one first
                if (profiles.Count > 0)
                {
                    try { profiles.Item(profiles.Count).Delete(); } catch { }
                }

                dynamic tempProfile = profiles.AddForSolid(false);
                var info = new Dictionary<string, object?> { ["index"] = i };

                // Delete all paths except the one at index i
                int pathIdx = 1;
                try
                {
                    var pathsToDelete = new System.Collections.Generic.List<object>();
                    foreach (dynamic path in tempProfile)
                    {
                        if (pathIdx != i)
                            pathsToDelete.Add(path);
                        pathIdx++;
                    }
                    foreach (dynamic path in pathsToDelete)
                        path.Delete();
                }
                catch { }

                // Read RegionProperties of the remaining single-path profile
                try
                {
                    dynamic region = tempProfile.RegionProperties;
                    info["area"] = Math.Round((double)region.Area, 4);
                    info["perimeter"] = Math.Round((double)region.Perimeter, 4);

                    try
                    {
                        dynamic centroid = region.Centroid;
                        info["centroid_x"] = Math.Round((double)centroid.X, 4);
                        info["centroid_y"] = Math.Round((double)centroid.Y, 4);
                    }
                    catch
                    {
                        info["centroid_x"] = null;
                        info["centroid_y"] = null;
                    }
                }
                catch
                {
                    info["area"] = null;
                    info["perimeter"] = null;
                }

                profileList.Add(info);
            }

            // Final cleanup: recreate a clean profile for downstream use
            if (profiles.Count > 0)
            {
                try { profiles.Item(profiles.Count).Delete(); } catch { }
            }
            profiles.AddForSolid(false);

            // Sort profiles by centroid position for predictable indexing:
            // top-to-bottom (Y desc), then left-to-right (X asc)
            profileList.Sort((a, b) =>
            {
                double ay = a.TryGetValue("centroid_y", out var cyObj) && cyObj is double cyVal ? cyVal : 0;
                double by = b.TryGetValue("centroid_y", out var cyObj2) && cyObj2 is double cyVal2 ? cyVal2 : 0;
                double ax = a.TryGetValue("centroid_x", out var cxObj) && cxObj is double cxVal ? cxVal : 0;
                double bx = b.TryGetValue("centroid_x", out var cxObj2) && cxObj2 is double cxVal2 ? cxVal2 : 0;

                int yCmp = by.CompareTo(ay); // descending Y
                if (yCmp != 0) return yCmp;
                return ax.CompareTo(bx); // ascending X
            });

            // Re-index after sorting
            for (int i = 0; i < profileList.Count; i++)
                profileList[i]["index"] = i + 1;

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["profile_count"] = pathCount,
                ["profiles"] = profileList,
                ["hint"] = pathCount > 1
                    ? $"Profiles sorted top→bottom, left→right. Use profile index (1-{pathCount}) in extrude/revolve."
                    : "Only one profile found — use profile=\"1\" or omit the parameter.",
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to list profiles: {ex.Message}", ex); }
    }

    public Dictionary<string, object?> SketchCircle(double cx, double cy, double radius, string? tag = null)
    {
        var sketch = EnsureActiveSketch();
        try
        {
            var tg = TransientGeometry();
            dynamic center = tg.CreatePoint2d(cx, cy);
            sketch.SketchCircles.AddByCenterRadius(center, radius);
            if (!string.IsNullOrEmpty(tag))
            {
                int entityIdx = sketch.SketchEntities.Count;
                int typeIdx = sketch.SketchCircles.Count;
                TagStore.SetTag(_activeSketchIndex, entityIdx, tag,
                    TagStore.EntityType.SketchCircle, typeIdx);
            }
            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["entity_type"] = "circle",
                ["center"] = new[] { cx, cy },
                ["radius"] = radius,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to draw circle: {ex.Message}", ex); }
    }

    public Dictionary<string, object?> SketchArc(double cx, double cy, double radius, double startAngle, double endAngle)
    {
        var sketch = EnsureActiveSketch();
        try
        {
            var tg = TransientGeometry();
            var center = tg.CreatePoint2d(cx, cy);
            var planarSketch = (global::Inventor.PlanarSketch)sketch;
            // AddByCenterStartSweepAngle expects RADIANS, not degrees
            double sweepAngle = endAngle - startAngle;
            double startAngleRad = startAngle * Math.PI / 180.0;
            double sweepAngleRad = sweepAngle * Math.PI / 180.0;
            planarSketch.SketchArcs.AddByCenterStartSweepAngle(center, radius, startAngleRad, sweepAngleRad);
            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["entity_type"] = "arc",
                ["center"] = new[] { cx, cy },
                ["radius"] = radius,
                ["start_angle"] = startAngle,
                ["end_angle"] = endAngle,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to draw arc: {ex.Message}", ex); }
    }

    public Dictionary<string, object?> SketchRectangle(double x1, double y1, double x2, double y2)
    {
        var sketch = EnsureActiveSketch();
        try
        {
            var tg = TransientGeometry();
            dynamic corner1 = tg.CreatePoint2d(x1, y1);
            dynamic corner2 = tg.CreatePoint2d(x2, y2);
            sketch.SketchLines.AddAsTwoPointRectangle(corner1, corner2);
            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["entity_type"] = "rectangle",
                ["corner1"] = new[] { x1, y1 },
                ["corner2"] = new[] { x2, y2 },
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to draw rectangle: {ex.Message}", ex); }
    }

    public Dictionary<string, object?> SketchPoint(double x, double y)
    {
        var sketch = EnsureActiveSketch();
        try
        {
            var tg = TransientGeometry();
            dynamic pt = tg.CreatePoint2d(x, y);
            sketch.SketchPoints.Add(pt);
            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["entity_type"] = "point",
                ["x"] = x,
                ["y"] = y,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to draw point: {ex.Message}", ex); }
    }

    public Dictionary<string, object?> SketchSpline(string points, string fitMethod = "sweet")
    {
        if (!SplineFitMethods.TryGetValue(fitMethod, out int methodEnum))
            return ErrorResult.Create($"Unknown fit method '{fitMethod}'. Use: smooth, sweet, autocad");

        var sketch = EnsureActiveSketch();
        try
        {
            var tg = TransientGeometry();
            var col = App.TransientObjects.CreateObjectCollection();
            var parts = points.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
            if (parts.Length < 4 || parts.Length % 2 != 0)
                return ErrorResult.Create("points must be comma-separated x,y pairs with at least 3 points");

            for (int i = 0; i < parts.Length; i += 2)
            {
                double px = double.Parse(parts[i]);
                double py = double.Parse(parts[i + 1]);
                col.Add(tg.CreatePoint2d(px, py));
            }

            var planarSketch = (global::Inventor.PlanarSketch)sketch;
            planarSketch.SketchSplines.Add(col, (global::Inventor.SplineFitMethodEnum)methodEnum);
            int pointCount = parts.Length / 2;
            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["entity_type"] = "spline",
                ["points"] = pointCount,
                ["fit_method"] = fitMethod,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to draw spline: {ex.Message}", ex); }
    }

    public Dictionary<string, object?> SketchEllipse(
        double cx, double cy, double majorRadius, double minorRadius, double majorAxisAngle = 0.0)
    {
        var sketch = EnsureActiveSketch();
        try
        {
            var tg = TransientGeometry();
            var center = tg.CreatePoint2d(cx, cy);
            double rad = majorAxisAngle * Math.PI / 180.0;
            var axisVec = (global::Inventor.UnitVector2d)tg.CreateUnitVector2d(Math.Cos(rad), Math.Sin(rad));
            var planarSketch = (global::Inventor.PlanarSketch)sketch;
            planarSketch.SketchEllipses.Add(center, axisVec, majorRadius, minorRadius);
            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["entity_type"] = "ellipse",
                ["cx"] = cx,
                ["cy"] = cy,
                ["major_radius"] = majorRadius,
                ["minor_radius"] = minorRadius,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to draw ellipse: {ex.Message}", ex); }
    }

    public Dictionary<string, object?> SketchCircularPattern(
        string entities, string axis, int count,
        double angle = 360.0, bool fitted = true, bool symmetric = false)
    {
        var sketch = EnsureActiveSketch();
        try
        {
            var col = BuildEntityCollection(sketch, entities);

            // Resolve center point from axis (1-based index into SketchPoints)
            int axisIndex = int.Parse(axis.Trim());
            dynamic centerPt = sketch.SketchPoints.Item(axisIndex);

            double angleRad = angle * Math.PI / 180.0;

            var cp = sketch.CircularPatterns;
            // CreateDefinition(Geometries, AxisEntity, NaturalAxisDirection, Count, Angle, Symmetric, Associative, Fitted)
            object? natDir = true; // default natural direction
            dynamic definition = cp.CreateDefinition(col, centerPt, natDir, count, angleRad, symmetric, Type.Missing, fitted);
            cp.Add(definition);

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["pattern_type"] = "sketch_circular",
                ["count"] = count,
                ["angle"] = angle,
                ["fitted"] = fitted,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to create sketch circular pattern: {ex.Message}", ex); }
    }

    public Dictionary<string, object?> SketchRectangularPattern(
        string entities, string xAxis, int xCount, double xSpacing,
        string yAxis = "", int yCount = 1, double ySpacing = 0.0)
    {
        var sketch = EnsureActiveSketch();
        try
        {
            var col = BuildEntityCollection(sketch, entities);
            dynamic xDir = sketch.SketchEntities.Item(int.Parse(xAxis.Trim()));

            var rp = sketch.RectangularPatterns;
            dynamic definition;

            if (!string.IsNullOrEmpty(yAxis))
            {
                dynamic yDir = sketch.SketchEntities.Item(int.Parse(yAxis.Trim()));
                definition = rp.CreateDefinition(
                    col, xDir, xCount,
                    Type.Missing, Type.Missing, xSpacing,
                    yDir, yCount, Type.Missing, Type.Missing, ySpacing);
            }
            else
            {
                definition = rp.CreateDefinition(
                    col, xDir, xCount,
                    Type.Missing, Type.Missing, xSpacing);
            }

            rp.Add(definition);
            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["pattern_type"] = "sketch_rectangular",
                ["x_count"] = xCount,
                ["y_count"] = yCount,
                ["x_spacing"] = xSpacing,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to create sketch rectangular pattern: {ex.Message}", ex); }
    }

    /// <summary>
    /// Retrieves a sketch entity by index from the appropriate type-specific
    /// collection. OffsetSketchEntitiesUsingPoint requires the concrete type
    /// (SketchCircle, SketchLine, etc.), not the base SketchEntity that
    /// SketchEntities.Item() returns. MoveSketchObjects/RotateSketchObjects
    /// are more permissive and work with the base type.
    /// </summary>
    private static dynamic GetTypedEntity(dynamic sketch, int index)
    {
        // Try each type-specific collection; fall back to SketchEntities
        try { return sketch.SketchCircles.Item(index); }    catch { }
        try { return sketch.SketchLines.Item(index); }      catch { }
        try { return sketch.SketchArcs.Item(index); }       catch { }
        try { return sketch.SketchSplines.Item(index); }    catch { }
        try { return sketch.SketchPoints.Item(index); }     catch { }
        try { return sketch.SketchEllipses.Item(index); }   catch { }
        return sketch.SketchEntities.Item(index);
    }

    public Dictionary<string, object?> SketchOffset(
        string entities, double offsetX, double offsetY, bool includeConnected = false)
    {
        var sketch = EnsureActiveSketch();
        try
        {
            // OffsetSketchEntitiesUsingPoint needs type-specific entity
            // references (SketchCircle, etc.), not base SketchEntity.
            // Collection and point must be built via late-bound (dynamic)
            // to preserve COM identity.
            dynamic to = App.TransientObjects;
            dynamic col = to.CreateObjectCollection();
            foreach (var idxStr in entities.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
            {
                col.Add(GetTypedEntity(sketch, int.Parse(idxStr)));
            }

            var tg = TransientGeometry();
            dynamic offsetPt = tg.CreatePoint2d(offsetX, offsetY);

            ((dynamic)sketch).OffsetSketchEntitiesUsingPoint(col, offsetPt, includeConnected, true);
            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["operation"] = "offset",
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to offset sketch: {ex.Message}", ex); }
    }

    public Dictionary<string, object?> SketchMove(string entities, double dx, double dy, bool copy = false)
    {
        var sketch = EnsureActiveSketch();
        try
        {
            var col = (global::Inventor.ObjectCollection)BuildEntityCollection(sketch, entities);
            var tg = TransientGeometry();
            var vec = (global::Inventor.Vector2d)tg.CreateVector2d(dx, dy);
            var planarSketch = (global::Inventor.PlanarSketch)sketch;
            planarSketch.MoveSketchObjects(col, vec, copy, false);
            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["operation"] = "move",
                ["dx"] = dx,
                ["dy"] = dy,
                ["copy"] = copy,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to move sketch: {ex.Message}", ex); }
    }

    public Dictionary<string, object?> SketchRotate(
        string entities, double cx, double cy, double angle, bool copy = false)
    {
        var sketch = EnsureActiveSketch();
        try
        {
            var col = (global::Inventor.ObjectCollection)BuildEntityCollection(sketch, entities);
            var tg = TransientGeometry();
            var center = (global::Inventor.Point2d)tg.CreatePoint2d(cx, cy);
            double angleRad = angle * Math.PI / 180.0;
            var planarSketch = (global::Inventor.PlanarSketch)sketch;
            planarSketch.RotateSketchObjects(col, center, angleRad, copy, false);
            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["operation"] = "rotate",
                ["angle"] = angle,
                ["cx"] = cx,
                ["cy"] = cy,
                ["copy"] = copy,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to rotate sketch: {ex.Message}", ex); }
    }

    public Dictionary<string, object?> SketchDelete()
    {
        var sketch = EnsureActiveSketch();
        try
        {
            sketch.Delete();
            _activeSketch = null;
            _activeSketchIndex = 0;
            _lastEndpoint = null;
            _firstStartpoint = null;
            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["operation"] = "delete_sketch",
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to delete sketch: {ex.Message}", ex); }
    }

    public Dictionary<string, object?> SketchConstraint(
        string mode, string entity1, string entity2 = "",
        string symLine = "", string axis = "major")
    {
        var sketch = EnsureActiveSketch();
        try
        {
            var gc = sketch.GeometricConstraints;
            bool useMajor = !axis.Equals("minor", StringComparison.OrdinalIgnoreCase);

            // Typed collection resolution
            var lineModes = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
                { "parallel", "perpendicular", "collinear", "horizontal", "vertical", "equal" };
            var circleModes = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
                { "concentric", "tangent" };
            var pointModes = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
                { "midpoint" };

            dynamic e1, e2 = Type.Missing;

            if (lineModes.Contains(mode))
            {
                e1 = sketch.SketchLines.Item(int.Parse(entity1.Trim()));
                if (!string.IsNullOrEmpty(entity2))
                    e2 = sketch.SketchLines.Item(int.Parse(entity2.Trim()));
            }
            else if (circleModes.Contains(mode))
            {
                e1 = sketch.SketchCircles.Item(int.Parse(entity1.Trim()));
                if (!string.IsNullOrEmpty(entity2))
                    e2 = sketch.SketchCircles.Item(int.Parse(entity2.Trim()));
            }
            else if (pointModes.Contains(mode))
            {
                e1 = sketch.SketchPoints.Item(int.Parse(entity1.Trim()));
                if (!string.IsNullOrEmpty(entity2))
                    e2 = sketch.SketchPoints.Item(int.Parse(entity2.Trim()));
            }
            else
            {
                e1 = sketch.SketchEntities.Item(int.Parse(entity1.Trim()));
                if (!string.IsNullOrEmpty(entity2))
                    e2 = sketch.SketchEntities.Item(int.Parse(entity2.Trim()));
            }

            switch (mode.ToLowerInvariant())
            {
                case "coincident":
                    // Coincident: entity1 = SketchPoint, entity2 = any SketchEntity (line, circle, arc, point, etc.)
                    // AddCoincident(point, entity) constrains the point to lie ON the entity.
                    {
                        dynamic pointEnt = sketch.SketchPoints.Item(int.Parse(entity1.Trim()));
                        dynamic entityEnt = sketch.SketchEntities.Item(int.Parse(entity2.Trim()));
                        gc.AddCoincident(pointEnt, entityEnt);
                    }
                    break;
                case "collinear":
                    gc.AddCollinear(e1, e2, useMajor, useMajor);
                    break;
                case "concentric":
                    gc.AddConcentric(e1, e2);
                    break;
                case "parallel":
                    gc.AddParallel(e1, e2, useMajor, useMajor);
                    break;
                case "perpendicular":
                    gc.AddPerpendicular(e1, e2, useMajor, useMajor);
                    break;
                case "tangent":
                    gc.AddTangent(e1, e2);
                    break;
                case "equal":
                    gc.AddEqualLength(e1, e2);
                    break;
                case "midpoint":
                    gc.AddMidpoint(e1, e2);
                    break;
                case "symmetric":
                    if (string.IsNullOrEmpty(symLine))
                        return ErrorResult.Create("Symmetric constraint needs sym_line parameter");
                    dynamic symEntity = sketch.SketchEntities.Item(int.Parse(symLine.Trim()));
                    gc.AddSymmetry(e1, e2, symEntity);
                    break;
                case "smooth":
                    gc.AddSmooth(e1, e2);
                    break;
                case "horizontal":
                    gc.AddHorizontal(e1, useMajor);
                    break;
                case "vertical":
                    gc.AddVertical(e1, useMajor);
                    break;
                default:
                    return ErrorResult.Create($"Unknown constraint mode '{mode}'");
            }

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["constraint"] = mode.ToLowerInvariant(),
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to add {mode} constraint: {ex.Message}", ex); }
    }

    public Dictionary<string, object?> SketchDimension(
        string mode, string entity1, string entity2 = "",
        double? value = null, string orientation = "aligned",
        double? positionX = null, double? positionY = null)
    {
        var sketch = EnsureActiveSketch();
        try
        {
            var dc = sketch.DimensionConstraints;
            var tg = TransientGeometry();

            // Resolve entity from typed collection
            dynamic e1;
            if (mode.Equals("radius", StringComparison.OrdinalIgnoreCase) ||
                mode.Equals("diameter", StringComparison.OrdinalIgnoreCase))
            {
                e1 = sketch.SketchCircles.Item(int.Parse(entity1.Trim()));
            }
            else if (mode.Equals("angle", StringComparison.OrdinalIgnoreCase))
            {
                e1 = sketch.SketchLines.Item(int.Parse(entity1.Trim()));
            }
            else
            {
                e1 = sketch.SketchEntities.Item(int.Parse(entity1.Trim()));
            }

            // Determine text position
            dynamic textPt;
            if (positionX.HasValue && positionY.HasValue)
            {
                textPt = tg.CreatePoint2d(positionX.Value, positionY.Value);
            }
            else
            {
                // Default: offset from entity geometry
                double mx = 5.0, my = 5.0;
                try
                {
                    dynamic g = e1.Geometry;
                    try
                    {
                        // Line-style geometry
                        mx = (g.StartPoint.X + g.EndPoint.X) / 2.0 + 2.0;
                        my = (g.StartPoint.Y + g.EndPoint.Y) / 2.0 + 2.0;
                    }
                    catch
                    {
                        // Circle-style geometry
                        mx = g.Center.X + 2.0;
                        my = g.Center.Y + 2.0;
                    }
                }
                catch { /* fallback defaults */ }
                textPt = tg.CreatePoint2d(mx, my);
            }

            dynamic dim;
            if (mode.Equals("linear", StringComparison.OrdinalIgnoreCase))
            {
                var pt1 = sketch.SketchPoints.Item(int.Parse(entity1.Trim()));
                var pt2 = !string.IsNullOrEmpty(entity2)
                    ? sketch.SketchPoints.Item(int.Parse(entity2.Trim()))
                    : sketch.SketchPoints.Item(int.Parse(entity1.Trim()) + 1);

                int orient = DimensionOrientations.GetValueOrDefault(orientation, 19203); // aligned default
                dim = dc.AddTwoPointDistance(pt1, pt2, orient, textPt);
            }
            else if (mode.Equals("radius", StringComparison.OrdinalIgnoreCase))
            {
                dim = dc.AddRadius(e1, textPt, false);
            }
            else if (mode.Equals("diameter", StringComparison.OrdinalIgnoreCase))
            {
                dim = dc.AddDiameter(e1, textPt, false);
            }
            else if (mode.Equals("angle", StringComparison.OrdinalIgnoreCase))
            {
                if (string.IsNullOrEmpty(entity2))
                    return ErrorResult.Create("Angle dimension mode needs entity2 (second line)");
                dynamic e2 = sketch.SketchLines.Item(int.Parse(entity2.Trim()));
                dim = dc.AddTwoLineAngle(e1, e2, textPt);
            }
            else
            {
                return ErrorResult.Create($"Unknown dimension mode '{mode}'");
            }

            if (value.HasValue)
                dim.Parameter.Value = value.Value;

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["entity_type"] = "dimension",
                ["mode"] = mode,
                ["value"] = value,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to add dimension: {ex.Message}", ex); }
    }

    public Dictionary<string, object?> SketchTrim(string entity, string cuttingEntity, string side = "end")
    {
        var sketch = EnsureActiveSketch();
        try
        {
            var planarSketch = (global::Inventor.PlanarSketch)sketch;

            // SketchEntities.Item() returns SketchEntity (base type), not SketchLine.
            // Use dynamic dispatch to access SketchLine-specific members (StartSketchPoint, etc.)
            // without requiring a cast that would fail with E_NOINTERFACE.
            dynamic ent = planarSketch.SketchEntities[int.Parse(entity.Trim())];
            dynamic cut = planarSketch.SketchEntities[int.Parse(cuttingEntity.Trim())];

            // Get endpoints via dynamic dispatch
            double x1 = (double)ent.StartSketchPoint.Geometry.X;
            double y1 = (double)ent.StartSketchPoint.Geometry.Y;
            double x2 = (double)ent.EndSketchPoint.Geometry.X;
            double y2 = (double)ent.EndSketchPoint.Geometry.Y;

            double x3 = (double)cut.StartSketchPoint.Geometry.X;
            double y3 = (double)cut.StartSketchPoint.Geometry.Y;
            double x4 = (double)cut.EndSketchPoint.Geometry.X;
            double y4 = (double)cut.EndSketchPoint.Geometry.Y;

            // Compute line-line intersection
            double denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4);
            if (Math.Abs(denom) < 1e-12)
                return ErrorResult.Create("Entities are parallel — no intersection");

            double t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom;
            double ix = x1 + t * (x2 - x1);
            double iy = y1 + t * (y2 - y1);

            // Determine which side to keep
            bool trimStart = side.Equals("start", StringComparison.OrdinalIgnoreCase);
            double sx = trimStart ? ix : x1;
            double sy = trimStart ? iy : y1;
            double ex = trimStart ? x2 : ix;
            double ey = trimStart ? y2 : iy;

            // Delete original and recreate trimmed line
            ent.Delete();
            var tg = TransientGeometry();
            planarSketch.SketchLines.AddByTwoPoints(
                (global::Inventor.Point2d)tg.CreatePoint2d(sx, sy),
                (global::Inventor.Point2d)tg.CreatePoint2d(ex, ey));

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["operation"] = "trim",
                ["side"] = side,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to trim: {ex.Message}", ex); }
    }

    public Dictionary<string, object?> SketchScale(string entities, double cx, double cy, double factor)
    {
        var sketch = EnsureActiveSketch();
        try
        {
            // Note: No ScaleSketchObjects method in Inventor interop; using manual point calculation
            var planarSketch = (global::Inventor.PlanarSketch)sketch;
            var tg = TransientGeometry();
            foreach (var idxStr in entities.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
            {
                dynamic ent = planarSketch.SketchLines[int.Parse(idxStr)];
                var start = (global::Inventor.SketchPoint)ent.StartSketchPoint;
                var end = (global::Inventor.SketchPoint)ent.EndSketchPoint;

                double sgX = start.Geometry.X, sgY = start.Geometry.Y;
                double egX = end.Geometry.X, egY = end.Geometry.Y;

                double nx1 = cx + (sgX - cx) * factor;
                double ny1 = cy + (sgY - cy) * factor;
                double nx2 = cx + (egX - cx) * factor;
                double ny2 = cy + (egY - cy) * factor;

                start.MoveTo((global::Inventor.Point2d)tg.CreatePoint2d(nx1, ny1));
                end.MoveTo((global::Inventor.Point2d)tg.CreatePoint2d(nx2, ny2));
            }

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["operation"] = "scale",
                ["factor"] = factor,
                ["cx"] = cx,
                ["cy"] = cy,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to scale: {ex.Message}", ex); }
    }

    public Dictionary<string, object?> SketchMirror(string entities, string mirrorEntity)
    {
        var sketch = EnsureActiveSketch();
        try
        {
            // Note: No Mirror method on PlanarSketch in Inventor interop; using manual reflection math
            var planarSketch = (global::Inventor.PlanarSketch)sketch;
            dynamic mirrorLine = planarSketch.SketchLines[int.Parse(mirrorEntity.Trim())];
            dynamic mg = mirrorLine.Geometry;

            // Mirror axis line endpoints
            double ax1 = mg.StartPoint.X, ay1 = mg.StartPoint.Y;
            double ax2 = mg.EndPoint.X, ay2 = mg.EndPoint.Y;
            double vx = ax2 - ax1, vy = ay2 - ay1;
            double vlen2 = vx * vx + vy * vy;

            if (vlen2 < 1e-12)
                return ErrorResult.Create("Mirror line has zero length");

            var tg = TransientGeometry();

            foreach (var idxStr in entities.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
            {
                dynamic ent = planarSketch.SketchLines[int.Parse(idxStr)];
                var start = (global::Inventor.SketchPoint)ent.StartSketchPoint;
                var end = (global::Inventor.SketchPoint)ent.EndSketchPoint;

                double sgX = start.Geometry.X, sgY = start.Geometry.Y;
                double egX = end.Geometry.X, egY = end.Geometry.Y;

                // Reflect start point
                double dx = sgX - ax1, dy = sgY - ay1;
                double t = (dx * vx + dy * vy) / vlen2;
                double rcx = ax1 + t * vx, rcy = ay1 + t * vy;
                double rx1 = 2.0 * rcx - sgX, ry1 = 2.0 * rcy - sgY;

                // Reflect end point
                dx = egX - ax1; dy = egY - ay1;
                t = (dx * vx + dy * vy) / vlen2;
                rcx = ax1 + t * vx; rcy = ay1 + t * vy;
                double rx2 = 2.0 * rcx - egX, ry2 = 2.0 * rcy - egY;

                start.MoveTo((global::Inventor.Point2d)tg.CreatePoint2d(rx1, ry1));
                end.MoveTo((global::Inventor.Point2d)tg.CreatePoint2d(rx2, ry2));
            }

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["operation"] = "mirror",
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to mirror: {ex.Message}", ex); }
    }
}