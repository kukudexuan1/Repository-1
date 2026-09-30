using System.Text.Json;
using McpCad.Core.Exceptions;
using McpCad.Core.Models;
using McpCad.Inventor.Helpers;
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using InvApp = Inventor.Application;

namespace McpCad.Inventor.Managers;

/// <summary>
/// Provides inspection tools for LLM feedback loops:
/// - CaptureViewportImage: screenshot of the 3D view (Base64) for multimodal vision verification.
/// - GetFeatureTree: structured tree of operations/features for data-driven "Árbol de Operaciones" inspection.
/// - GetBoundingBox: direct geometry bounds for verification without images.
/// 
/// These enable the two approaches described by the user for retroalimentación de imágenes / visual + data feedback.
/// </summary>
public class InspectionManager(InventorDriver driver)
{
    private InvApp App => driver.InventorApp;

    private dynamic ActiveDocument()
    {
        var doc = driver.ActiveDocument
            ?? throw new InventorComException("No active document. Open or create a document first.");
        return doc;
    }

    private dynamic ComponentDefinition()
    {
        var compDef = driver.ComponentDefinition
            ?? throw new InventorComException("No component definition available.");
        return ComDispatchHelper.WrapDispatch(compDef);
    }

    /// <summary>
    /// Captures a screenshot of the current viewport.
    /// Returns Base64 image so the LLM (vision model) can analyze the visual state after a tool call.
    /// 
    /// TODO for full viewport accuracy: Provide exact Inventor COM call for ActiveView bitmap capture.
    /// Current implementation uses a simple approach (temp file if possible) or placeholder.
    /// Common patterns: app.ActiveView, Camera, or window HWND + GDI BitBlt.
    /// </summary>
    public Dictionary<string, object?> CaptureViewportImage(string view = "Iso", int width = 1024, int height = 768, string format = "png")
    {
        try
        {
            var doc = ActiveDocument();

            // Reliable approach per Inventor API limitations (as discussed):
            // 1. (Optionally) set the desired standard view orientation on the active viewport.
            // 2. SaveAs to a temporary image file (lifetime = milliseconds).
            // 3. Read the bytes immediately.
            // 4. Convert to Base64.
            // 5. Delete the temp file right away.
            // This gives the LLM a visual snapshot of the current 3D state for vision-model verification.

            string tempPath = Path.Combine(Path.GetTempPath(), $"mcp_viewport_{Guid.NewGuid():N}.{format}");

            // Try to orient the view (Iso, Front, Top, etc.)
            try
            {
                dynamic activeView = App.ActiveView;
                if (activeView != null)
                {
                    dynamic camera = activeView.Camera;
                    int orientation = 10754; // default good isometric
                    string v = (view ?? "iso").ToLowerInvariant();
                    if (v.Contains("front")) orientation = 10753;
                    else if (v.Contains("top")) orientation = 10755;
                    else if (v.Contains("right")) orientation = 10757;
                    else if (v.Contains("iso")) orientation = 10754;

                    camera.ViewOrientationType = orientation;
                    camera.ApplyWithoutTransition();
                }
            }
            catch { /* non-fatal */ }

            // Export to temp (the proven reliable path)
            doc.SaveAs(tempPath, true);

            if (!File.Exists(tempPath))
            {
                return new Dictionary<string, object?>
                {
                    ["success"] = false,
                    ["error"] = "SaveAs did not produce the expected image file.",
                    ["note"] = "If this does not capture the rendered 3D viewport you want, provide the exact Inventor COM code (ActiveView + Camera or graphics render) and I'll integrate it."
                };
            }

            byte[] imageBytes = File.ReadAllBytes(tempPath);
            string base64 = Convert.ToBase64String(imageBytes);

            try { File.Delete(tempPath); } catch { /* best effort */ }

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["view"] = view,
                ["width"] = width,
                ["height"] = height,
                ["format"] = format,
                ["mime_type"] = format.Equals("png", StringComparison.OrdinalIgnoreCase) ? "image/png" : "image/jpeg",
                ["image_base64"] = base64
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex)
        {
            throw new InventorComException($"CaptureViewportImage failed: {ex.Message}", ex);
        }
    }

    /// <summary>
    /// Builds a recursive tree of the features/operations in the active document.
    /// This implements the "Árbol de Operaciones" approach: the LLM can read the exact structure
    /// (names, types, order, suppression) directly from the Inventor object model.
    /// </summary>
    public Dictionary<string, object?> GetFeatureTree()
    {
        try
        {
            var compDef = ComponentDefinition();
            var features = new List<Dictionary<string, object?>>();

            // For parts
            try
            {
                dynamic partFeatures = compDef.Features;
                if (partFeatures != null)
                {
                    foreach (dynamic f in partFeatures)
                    {
                        features.Add(FeatureToDict(f));
                    }
                }
            }
            catch { /* not a part or no features collection at this level */ }

            // For assemblies - list occurrences as top level "features" of the tree (with their sub-features if loaded)
            try
            {
                dynamic occurrences = compDef.Occurrences;
                if (occurrences != null)
                {
                    foreach (dynamic occ in occurrences)
                    {
                        var occDict = new Dictionary<string, object?>
                        {
                            ["name"] = occ.Name?.ToString(),
                            ["type"] = "Occurrence",
                            ["path"] = occ.ReferencedDocumentDescriptor?.FullDocumentName,
                            ["grounded"] = occ.Grounded,
                            ["suppressed"] = occ.Suppressed,
                        };
                        features.Add(occDict);
                    }
                }
            }
            catch { /* not assembly or no occurrences */ }

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["document_type"] = compDef.Type?.ToString() ?? "unknown",
                ["feature_count"] = features.Count,
                ["tree"] = features,
                ["note"] = "Tree contains top-level features/occurrences. For deeper sub-features or constraints, extend the traversal as needed."
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex)
        {
            throw new InventorComException($"GetFeatureTree failed: {ex.Message}", ex);
        }
    }

    private Dictionary<string, object?> FeatureToDict(dynamic feature)
    {
        var dict = new Dictionary<string, object?>
        {
            ["name"] = feature.Name?.ToString(),
            ["type"] = feature.Type?.ToString() ?? feature.GetType().Name,
            ["suppressed"] = feature.Suppressed,
        };

        // Try to get health or extent info if available
        try { dict["health"] = feature.HealthStatus?.ToString(); } catch { }
        try { dict["is_consumed"] = feature.IsConsumed; } catch { }

        // Recurse into sub features if the feature exposes them (patterns, etc.)
        try
        {
            dynamic sub = feature.Features;
            if (sub != null)
            {
                var subs = new List<Dictionary<string, object?>>();
                foreach (dynamic sf in sub)
                {
                    subs.Add(FeatureToDict(sf));
                }
                if (subs.Count > 0) dict["sub_features"] = subs;
            }
        }
        catch { }

        return dict;
    }

    /// <summary>
    /// Returns bounding box data for verification (min/max, center, size).
    /// Target can be empty (whole model), a body name, a tagged entity, or "all".
    /// Uses direct Inventor geometry API (no rendering).
    /// </summary>
    public Dictionary<string, object?> GetBodyCount()
    {
        var compDef = ComponentDefinition();
        int count = (int)compDef.SurfaceBodies.Count;
        return new Dictionary<string, object?> { ["success"] = true, ["body_count"] = count };
    }

    public Dictionary<string, object?> InspectFeature(string target)
    {
        try
        {
            var compDef = ComponentDefinition();
            dynamic features = compDef.Features;
            dynamic feature = int.TryParse(target, out int index) ? features.Item(index) : features.Item(target);
            var result = new Dictionary<string, object?>
            {
                ["success"] = true,
                ["name"] = feature.Name?.ToString(),
                ["type"] = feature.Type?.ToString(),
            };
            try { result["health"] = feature.HealthStatus?.ToString(); } catch { }
            try
            {
                dynamic box = feature.RangeBox;
                result["min"] = new { x = (double)box.MinPoint.X, y = (double)box.MinPoint.Y, z = (double)box.MinPoint.Z };
                result["max"] = new { x = (double)box.MaxPoint.X, y = (double)box.MaxPoint.Y, z = (double)box.MaxPoint.Z };
            }
            catch { }
            return result;
        }
        catch (Exception ex)
        {
            return new Dictionary<string, object?> { ["success"] = false, ["error"] = $"Feature '{target}' not found: {ex.Message}" };
        }
    }

    public Dictionary<string, object?> MeasureSection(string axis, double positionCm)
    {
        var compDef = ComponentDefinition();
        if (compDef.SurfaceBodies.Count != 1)
            return new Dictionary<string, object?> { ["success"] = false, ["error"] = "Section measurement requires exactly one solid body." };
        dynamic body = compDef.SurfaceBodies.Item(1);
        dynamic box = body.RangeBox;
        double diameter = axis.ToUpperInvariant() switch
        {
            "X" => Math.Max((double)box.MaxPoint.Y - (double)box.MinPoint.Y, (double)box.MaxPoint.Z - (double)box.MinPoint.Z),
            "Y" => Math.Max((double)box.MaxPoint.X - (double)box.MinPoint.X, (double)box.MaxPoint.Z - (double)box.MinPoint.Z),
            "Z" => Math.Max((double)box.MaxPoint.X - (double)box.MinPoint.X, (double)box.MaxPoint.Y - (double)box.MinPoint.Y),
            _ => -1,
        };
        return new Dictionary<string, object?>
        {
            ["success"] = diameter >= 0,
            ["axis"] = axis.ToUpperInvariant(),
            ["position_cm"] = positionCm,
            ["diameter_cm"] = diameter,
            ["measurement_kind"] = "range_box_fallback",
        };
    }

    public Dictionary<string, object?> MeasureSectionFromCylindricalFaces(string axis, double positionCm)
    {
        try
        {
            var compDef = ComponentDefinition();
            if (compDef.SurfaceBodies.Count != 1) return ErrorResult.Create("Section measurement requires exactly one solid body.");
            string requestedAxis = axis.ToUpperInvariant();
            double? diameter = null;
            foreach (dynamic face in compDef.SurfaceBodies.Item(1).Faces)
            {
                try
                {
                    dynamic cylinder = face.Geometry;
                    dynamic direction = cylinder.AxisVector;
                    bool aligned = requestedAxis == "X" ? Math.Abs((double)direction.X) > 0.999
                        : requestedAxis == "Y" ? Math.Abs((double)direction.Y) > 0.999
                        : requestedAxis == "Z" && Math.Abs((double)direction.Z) > 0.999;
                    if (!aligned) continue;
                    dynamic box = face.RangeBox;
                    double min = requestedAxis == "X" ? (double)box.MinPoint.X : requestedAxis == "Y" ? (double)box.MinPoint.Y : (double)box.MinPoint.Z;
                    double max = requestedAxis == "X" ? (double)box.MaxPoint.X : requestedAxis == "Y" ? (double)box.MaxPoint.Y : (double)box.MaxPoint.Z;
                    if (positionCm < min - 1e-6 || positionCm > max + 1e-6) continue;
                    double candidate = 2.0 * (double)cylinder.Radius;
                    if (diameter is null || candidate > diameter) diameter = candidate;
                }
                catch { }
            }
            if (diameter is null) return ErrorResult.Create($"No cylindrical face crosses {requestedAxis}={positionCm} cm.");
            return new Dictionary<string, object?> { ["success"] = true, ["axis"] = requestedAxis, ["position_cm"] = positionCm, ["diameter_cm"] = diameter.Value, ["measurement_kind"] = "cylindrical_face" };
        }
        catch (Exception ex) { return ErrorResult.Create($"Section measurement failed: {ex.Message}"); }
    }

    public Dictionary<string, object?> GetBoundingBox(string target = "")
    {
        try
        {
            var compDef = ComponentDefinition();

            dynamic? rangeBox = null;
            string resolvedTarget = string.IsNullOrWhiteSpace(target) ? "model" : target.Trim();
            if (resolvedTarget.Equals("model", StringComparison.OrdinalIgnoreCase) || resolvedTarget.Equals("all", StringComparison.OrdinalIgnoreCase))
            {
                try { rangeBox = compDef.RangeBox; } catch { }
            }
            else if (resolvedTarget.StartsWith("body:", StringComparison.OrdinalIgnoreCase))
            {
                string id = resolvedTarget[5..];
                dynamic bodies = compDef.SurfaceBodies;
                dynamic body = int.TryParse(id, out int index) ? bodies.Item(index) : bodies.Item(id);
                rangeBox = body.RangeBox;
            }
            else if (resolvedTarget.StartsWith("feature:", StringComparison.OrdinalIgnoreCase))
            {
                string id = resolvedTarget[8..];
                dynamic features = compDef.Features;
                dynamic feature = int.TryParse(id, out int index) ? features.Item(index) : features.Item(id);
                rangeBox = feature.RangeBox;
            }
            else
            {
                return new Dictionary<string, object?>
                {
                    ["success"] = false,
                    ["error"] = $"Unknown target '{target}'. Use model, body:<index|name>, or feature:<index|name>.",
                    ["target"] = target,
                };
            }

            if (rangeBox == null)
            {
                // Whole-model fallback only.
                try
                {
                    dynamic bodies = compDef.SurfaceBodies;
                    if (bodies != null && bodies.Count > 0)
                    {
                        rangeBox = bodies[1].RangeBox;
                    }
                }
                catch { }
            }

            if (rangeBox == null)
            {
                return new Dictionary<string, object?>
                {
                    ["success"] = false,
                    ["error"] = "Could not obtain RangeBox. Target the model or provide a specific body/occurrence.",
                    ["target"] = target
                };
            }

            var min = rangeBox!.MinPoint;
            var max = rangeBox!.MaxPoint;

            double dx = max.X - min.X;
            double dy = max.Y - min.Y;
            double dz = max.Z - min.Z;

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["target"] = string.IsNullOrWhiteSpace(target) ? "model" : target,
                ["min"] = new { x = (double)min.X, y = (double)min.Y, z = (double)min.Z },
                ["max"] = new { x = (double)max.X, y = (double)max.Y, z = (double)max.Z },
                ["size"] = new { x = dx, y = dy, z = dz },
                ["center"] = new { x = (min.X + max.X) / 2, y = (min.Y + max.Y) / 2, z = (min.Z + max.Z) / 2 },
                ["note"] = "Direct vector data from Inventor RangeBox. Use for precise geometric checks (no vision required)."
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex)
        {
            throw new InventorComException($"GetBoundingBox failed: {ex.Message}", ex);
        }
    }

    // ── Geometry classification helpers ──────────────────────────────
    // Uses Inventor SurfaceTypeEnum / CurveTypeEnum properties directly.
    // Late-bound COM dispatch returns integer values, not enum names.
    // kPlanarSurface=5890, kCylindricalSurface=5891, kConicalSurface=5892,
    // kSphericalSurface=5893, kToroidalSurface=5894, kBSplineSurface=5895
    // kLineCurve=5122, kCircleCurve=5123, kEllipseCurve=5124, kBsplineCurve=5125

    private static string ClassifyFaceType(dynamic face)
    {
        try
        {
            string s = face.SurfaceType.ToString();
            return s switch
            {
                "5890" => "PLANE",
                "5891" => "CYLINDER",
                "5892" => "CONE",
                "5893" => "SPHERE",
                "5894" => "TORUS",
                "5895" => "BSPLINE",
                _ when s.Contains("Planar") || s.Contains("Plane") => "PLANE",
                _ when s.Contains("Cylinder") => "CYLINDER",
                _ when s.Contains("Conical") || s.Contains("Cone") => "CONE",
                _ when s.Contains("Sphere") => "SPHERE",
                _ when s.Contains("Torus") || s.Contains("Toroid") => "TORUS",
                _ when s.Contains("Spline") => "BSPLINE",
                _ => s
            };
        }
        catch { return "OTHER"; }
    }

    private static string ClassifyEdgeType(dynamic edge)
    {
        try
        {
            string s = edge.CurveType.ToString();
            return s switch
            {
                "5122" => "LINE",
                "5123" => "CIRCLE",
                "5124" => "ELLIPSE",
                "5125" => "BSPLINE",
                "5126" => "BSPLINE",
                _ when s.Contains("Line") => "LINE",
                _ when s.Contains("Circle") => "CIRCLE",
                _ when s.Contains("Ellipse") => "ELLIPSE",
                _ when s.Contains("Spline") => "BSPLINE",
                _ => s
            };
        }
        catch { return "OTHER"; }
    }

    // face is passed directly; geometry object is accessed internally
    private static Dictionary<string, object?> FaceGeoParams(string surfType, dynamic face)
    {
        var p = new Dictionary<string, object?>();
        try
        {
            dynamic geom = face.Geometry;
            if (surfType == "PLANE")
            {
                dynamic n = geom.Normal; dynamic o = geom.RootPoint;
                p["normal"] = new double[] { (double)n.X, (double)n.Y, (double)n.Z };
                p["origin"] = new double[] { (double)o.X, (double)o.Y, (double)o.Z };
            }
            else if (surfType == "CYLINDER")
            {
                dynamic ax = geom.AxisVector; dynamic bp = geom.BasePoint;
                p["radius"]         = (double)geom.Radius;
                p["axis_direction"] = new double[] { (double)ax.X, (double)ax.Y, (double)ax.Z };
                p["axis_point"]     = new double[] { (double)bp.X, (double)bp.Y, (double)bp.Z };
            }
            else if (surfType == "CONE")
            {
                dynamic ax = geom.AxisVector;
                p["half_angle_deg"] = (double)geom.HalfAngle * 180.0 / Math.PI;
                p["axis_direction"] = new double[] { (double)ax.X, (double)ax.Y, (double)ax.Z };
            }
            else if (surfType == "SPHERE")
            {
                dynamic c = geom.CenterPoint;
                p["radius"] = (double)geom.Radius;
                p["center"] = new double[] { (double)c.X, (double)c.Y, (double)c.Z };
            }
            else if (surfType == "TORUS")
            {
                p["major_radius"] = (double)geom.MajorRadius;
                p["minor_radius"] = (double)geom.MinorRadius;
            }
        }
        catch { }
        return p;
    }

    // edge is passed directly; geometry object is accessed internally
    // Edge geo params — each property wrapped independently to survive partial COM failures
    private static Dictionary<string, object?> EdgeGeoParams(string curveType, dynamic edge)
    {
        var p = new Dictionary<string, object?>();
        dynamic geom;
        try { geom = edge.Geometry; } catch { return p; }

        if (curveType == "CIRCLE")
        {
            try { p["radius"] = (double)geom.Radius; } catch { }
            try { dynamic c = geom.Center; p["center"] = new double[]{(double)c.X,(double)c.Y,(double)c.Z}; } catch { }
            try { dynamic ax = geom.AxisVector; p["axis_direction"] = new double[]{(double)ax.X,(double)ax.Y,(double)ax.Z}; } catch { }
        }
        else if (curveType == "LINE")
        {
            try { dynamic d = geom.Direction; p["direction"] = new double[]{(double)d.X,(double)d.Y,(double)d.Z}; } catch { }
            try { dynamic r = geom.RootPoint; p["root_point"] = new double[]{(double)r.X,(double)r.Y,(double)r.Z}; } catch { }
        }
        else if (curveType == "ELLIPSE")
        {
            try { p["major_radius"] = (double)geom.MajorRadius; } catch { }
            try { p["minor_radius"] = (double)geom.MinorRadius; } catch { }
            if (!p.ContainsKey("major_radius")) try { p["major_radius"] = (double)geom.SemiMajorAxis; } catch { }
            if (!p.ContainsKey("minor_radius")) try { p["minor_radius"] = (double)geom.SemiMinorAxis; } catch { }
            // Fallback: derive semi-axes from start vertex distance to center
            if (!p.ContainsKey("major_radius") || !p.ContainsKey("minor_radius"))
            {
                double[]? cen = null;
                try { dynamic c = geom.Center;      cen = new double[]{(double)c.X,(double)c.Y,(double)c.Z}; } catch { }
                try { dynamic c = geom.CenterPoint; cen = new double[]{(double)c.X,(double)c.Y,(double)c.Z}; } catch { }
                if (cen != null)
                {
                    try
                    {
                        dynamic sv = edge.StartVertex;
                        double dx=(double)sv.Point.X-cen[0], dy=(double)sv.Point.Y-cen[1], dz=(double)sv.Point.Z-cen[2];
                        double r = Math.Sqrt(dx*dx+dy*dy+dz*dz);
                        if (r > 1e-10) { p.TryAdd("major_radius", r); p.TryAdd("minor_radius", r); }
                    }
                    catch { }
                }
            }
            try { dynamic c = geom.Center;      p["center"] = new double[]{(double)c.X,(double)c.Y,(double)c.Z}; } catch { }
            try { dynamic c = geom.CenterPoint; p["center"] = new double[]{(double)c.X,(double)c.Y,(double)c.Z}; } catch { }
            try { dynamic ax = geom.MajorAxisVector; p["major_axis"] = new double[]{(double)ax.X,(double)ax.Y,(double)ax.Z}; } catch { }
            try { dynamic ax = geom.MajorAxis;       p["major_axis"] = new double[]{(double)ax.X,(double)ax.Y,(double)ax.Z}; } catch { }
        }
        return p;
    }

    private static (double u, double v) GetUVMid(dynamic ep)
    {
        dynamic uv = ep.GetParamExtent();
        double uMin, uMax, vMin, vMax;
        try { uMin=(double)uv.MinPoint.X; uMax=(double)uv.MaxPoint.X; vMin=(double)uv.MinPoint.Y; vMax=(double)uv.MaxPoint.Y; }
        catch { uMin=(double)uv.MinU; uMax=(double)uv.MaxU; vMin=(double)uv.MinV; vMax=(double)uv.MaxV; }
        return ((uMin+uMax)/2.0, (vMin+vMax)/2.0);
    }

    private static double[]? GetUVRange(dynamic face)
    {
        try
        {
            dynamic uv = face.Evaluator.GetParamExtent();
            double uMin, uMax, vMin, vMax;
            try { uMin=(double)uv.MinPoint.X; uMax=(double)uv.MaxPoint.X; vMin=(double)uv.MinPoint.Y; vMax=(double)uv.MaxPoint.Y; }
            catch { uMin=(double)uv.MinU; uMax=(double)uv.MaxU; vMin=(double)uv.MinV; vMax=(double)uv.MaxV; }
            return [uMin, uMax, vMin, vMax];
        }
        catch { return null; }
    }

    // ── Geometry-based measurements (no SurfaceEvaluator double-param calls) ──

    // Collect all vertex points from a face's edges
    private static List<double[]> FaceVertexPoints(dynamic face)
    {
        var pts = new List<double[]>();
        var seen = new HashSet<string>();
        try
        {
            dynamic fedges = face.Edges;
            foreach (dynamic fe in fedges)
            {
                try
                {
                    foreach (dynamic v in new dynamic[] { fe.StartVertex, fe.StopVertex })
                    {
                        try
                        {
                            double x = (double)v.Point.X, y = (double)v.Point.Y, z = (double)v.Point.Z;
                            string key = $"{x:F8},{y:F8},{z:F8}";
                            if (seen.Add(key)) pts.Add([x, y, z]);
                        }
                        catch { }
                    }
                }
                catch { }
            }
        }
        catch { }
        return pts;
    }

    private static double[]? FaceRangeBox(dynamic face)
    {
        // Try direct property first
        try
        {
            dynamic box = face.RangeBox;
            double x0 = (double)box.MinPoint.X;
            return [x0, (double)box.MinPoint.Y, (double)box.MinPoint.Z,
                    (double)box.MaxPoint.X, (double)box.MaxPoint.Y, (double)box.MaxPoint.Z];
        }
        catch { }
        // Fallback: compute from vertices
        var pts = FaceVertexPoints(face);
        if (pts.Count == 0) return null;
        double mnX=pts[0][0], mnY=pts[0][1], mnZ=pts[0][2];
        double mxX=pts[0][0], mxY=pts[0][1], mxZ=pts[0][2];
        foreach (var p in pts)
        {
            mnX=Math.Min(mnX,p[0]); mnY=Math.Min(mnY,p[1]); mnZ=Math.Min(mnZ,p[2]);
            mxX=Math.Max(mxX,p[0]); mxY=Math.Max(mxY,p[1]); mxZ=Math.Max(mxZ,p[2]);
        }
        return [mnX, mnY, mnZ, mxX, mxY, mxZ];
    }

    // Centroid: average of unique vertex positions (good approximation for shaft faces)
    private static double[]? FaceCentroid(dynamic face)
    {
        var pts = FaceVertexPoints(face);
        if (pts.Count == 0) return null;
        double sx=0, sy=0, sz=0;
        foreach (var p in pts) { sx+=p[0]; sy+=p[1]; sz+=p[2]; }
        double n = pts.Count;
        return [sx/n, sy/n, sz/n];
    }

    // Normal from geometry (no SurfaceEvaluator)
    private static double[]? FaceNormal(string surfType, dynamic face)
    {
        try
        {
            dynamic geom = face.Geometry;
            if (surfType == "PLANE")
            {
                dynamic n = geom.Normal;
                return [(double)n.X, (double)n.Y, (double)n.Z];
            }
            if (surfType == "CYLINDER" || surfType == "CONE")
            {
                // Outward radial: centroid → subtract axis projection
                var cen = FaceCentroid(face);
                if (cen == null) return null;
                dynamic bp = geom.BasePoint;
                dynamic ax = geom.AxisVector;
                double rx = cen[0]-(double)bp.X, ry = cen[1]-(double)bp.Y, rz = cen[2]-(double)bp.Z;
                double dot = rx*(double)ax.X + ry*(double)ax.Y + rz*(double)ax.Z;
                double nx2 = rx-dot*(double)ax.X, ny2 = ry-dot*(double)ax.Y, nz2 = rz-dot*(double)ax.Z;
                double len = Math.Sqrt(nx2*nx2+ny2*ny2+nz2*nz2);
                if (len > 1e-10) return [nx2/len, ny2/len, nz2/len];
            }
            if (surfType == "SPHERE")
            {
                var cen = FaceCentroid(face);
                if (cen == null) return null;
                dynamic cp = geom.CenterPoint;
                double nx2=cen[0]-(double)cp.X, ny2=cen[1]-(double)cp.Y, nz2=cen[2]-(double)cp.Z;
                double len=Math.Sqrt(nx2*nx2+ny2*ny2+nz2*nz2);
                if (len > 1e-10) return [nx2/len, ny2/len, nz2/len];
            }
        }
        catch { }
        return null;
    }

    // Area from geometry
    private static double GetFaceArea(string surfType, dynamic face)
    {
        try
        {
            if (surfType == "CYLINDER")
            {
                dynamic geom = face.Geometry;
                double r = (double)geom.Radius;
                dynamic ax = geom.AxisVector;
                var box = FaceRangeBox(face);
                if (box == null) return 0;
                double dx=box[3]-box[0], dy=box[4]-box[1], dz=box[5]-box[2];
                double h = Math.Abs((double)ax.X)*dx + Math.Abs((double)ax.Y)*dy + Math.Abs((double)ax.Z)*dz;
                return 2.0*Math.PI*r*h;
            }
            if (surfType == "PLANE")
            {
                var box = FaceRangeBox(face);
                if (box == null) return 0;
                double dx=box[3]-box[0], dy=box[4]-box[1], dz=box[5]-box[2];
                double[] spans = [dx, dy, dz]; Array.Sort(spans);
                return spans[1]*spans[2];
            }
            if (surfType == "SPHERE")
            {
                double r = (double)face.Geometry.Radius;
                return 4.0*Math.PI*r*r;
            }
        }
        catch { }
        return 0.0;
    }

    // Edge length: LINE exact, CIRCLE from radius, ELLIPSE from semi-axes
    private static double GetEdgeLength(string curveType, dynamic edge)
    {
        try
        {
            if (curveType == "LINE")
            {
                dynamic sv=edge.StartVertex; dynamic ev=edge.StopVertex;
                double dx=(double)sv.Point.X-(double)ev.Point.X;
                double dy=(double)sv.Point.Y-(double)ev.Point.Y;
                double dz=(double)sv.Point.Z-(double)ev.Point.Z;
                return Math.Sqrt(dx*dx+dy*dy+dz*dz);
            }
            if (curveType == "CIRCLE")
            {
                dynamic geom = edge.Geometry;
                double r = (double)geom.Radius;
                try
                {
                    dynamic eval = edge.Evaluator;
                    double p1=(double)eval.StartParam, p2=(double)eval.EndParam;
                    return r*Math.Abs(p2-p1);
                }
                catch { return 2.0*Math.PI*r; }
            }
            if (curveType == "ELLIPSE")
            {
                double a = 0, b = 0;
                try { dynamic geom2 = edge.Geometry; a = (double)geom2.MajorRadius; b = (double)geom2.MinorRadius; } catch { }
                // Fallback: derive radius from start vertex distance to center
                if (a <= 0)
                {
                    try
                    {
                        dynamic geom2 = edge.Geometry;
                        double[]? cen = null;
                        try { dynamic c = geom2.Center;      cen = new double[]{(double)c.X,(double)c.Y,(double)c.Z}; } catch { }
                        try { dynamic c = geom2.CenterPoint; cen = new double[]{(double)c.X,(double)c.Y,(double)c.Z}; } catch { }
                        if (cen != null)
                        {
                            dynamic sv = edge.StartVertex;
                            double dx=(double)sv.Point.X-cen[0], dy=(double)sv.Point.Y-cen[1], dz=(double)sv.Point.Z-cen[2];
                            double r = Math.Sqrt(dx*dx+dy*dy+dz*dz);
                            if (r > 1e-10) { a = r; b = r; }
                        }
                    }
                    catch { }
                }
                if (b <= 0) b = a;
                if (a > 0)
                {
                    double h = Math.Pow(a-b,2)/Math.Pow(a+b,2);
                    return Math.PI*(a+b)*(1.0+3.0*h/(10.0+Math.Sqrt(4.0-3.0*h)));
                }
            }
        }
        catch { }
        return 0.0;
    }

    // Build two-level adjacency maps for a body in one pass.
    private static void BuildAdjacencyMaps(
        dynamic body,
        out Dictionary<string, int> edgeIdx,
        out Dictionary<string, List<int>> edgeFaces)
    {
        edgeIdx   = new Dictionary<string, int>();
        edgeFaces = new Dictionary<string, List<int>>();

        try
        {
            dynamic bedges = body.Edges; int ec = (int)bedges.Count;
            for (int i = 1; i <= ec; i++)
            {
                try
                {
                    dynamic e = ComDispatchHelper.WrapDispatch(bedges.Item(i));
                    string? k1 = EdgeKey(e); string? k2 = EdgeKeyReverse(e);
                    if (k1 != null) { edgeIdx.TryAdd(k1, i-1); edgeIdx.TryAdd(k2!, i-1); }
                }
                catch { }
            }
        }
        catch { }

        try
        {
            dynamic bfaces = body.Faces; int fc = (int)bfaces.Count;
            for (int fi = 1; fi <= fc; fi++)
            {
                try
                {
                    dynamic face = ComDispatchHelper.WrapDispatch(bfaces.Item(fi));
                    dynamic fedges = face.Edges;
                    foreach (dynamic fe in fedges)
                    {
                        try
                        {
                            string? k1 = EdgeKey(fe); string? k2 = EdgeKeyReverse(fe);
                            foreach (string? k in new[] { k1, k2 })
                            {
                                if (k == null) continue;
                                if (!edgeFaces.TryGetValue(k, out var lst))
                                { lst = new List<int>(); edgeFaces[k] = lst; }
                                if (!lst.Contains(fi-1)) lst.Add(fi-1);
                            }
                        }
                        catch { }
                    }
                }
                catch { }
            }
        }
        catch { }
    }

    // Build edge-index lookup for a body (kept for backward compat)
    private static Dictionary<string, int> BuildEdgeIndexMap(dynamic body)
    {
        Dictionary<string, int> idx;
        Dictionary<string, List<int>> dummy;
        BuildAdjacencyMaps(body, out idx, out dummy);
        return idx;
    }

    private static string? EdgeKey(dynamic edge)
    {
        try
        {
            dynamic sv = edge.StartVertex; dynamic ev = edge.StopVertex;
            return $"{(double)sv.Point.X:F6},{(double)sv.Point.Y:F6},{(double)sv.Point.Z:F6}|{(double)ev.Point.X:F6},{(double)ev.Point.Y:F6},{(double)ev.Point.Z:F6}";
        }
        catch { return null; }
    }

    private static string? EdgeKeyReverse(dynamic edge)
    {
        try
        {
            dynamic sv = edge.StartVertex; dynamic ev = edge.StopVertex;
            return $"{(double)ev.Point.X:F6},{(double)ev.Point.Y:F6},{(double)ev.Point.Z:F6}|{(double)sv.Point.X:F6},{(double)sv.Point.Y:F6},{(double)sv.Point.Z:F6}";
        }
        catch { return null; }
    }

    // ── Semantic enrichment helpers ──────────────────────────────────

    // 1. Arc span in degrees for a CYLINDER face.
    //    Finds the circular/elliptical edges, projects their start/end vertices
    //    onto the plane perpendicular to the axis, measures the swept angle.
    //    Returns 360 for a closed cylinder (hole/full surface), < 360 for fillet.
    private static double? CylinderArcSpan(dynamic face)
    {
        try
        {
            dynamic geom = face.Geometry;
            double ax = (double)geom.AxisVector.X;
            double ay = (double)geom.AxisVector.Y;
            double az = (double)geom.AxisVector.Z;
            double bx = (double)geom.BasePoint.X;
            double by = (double)geom.BasePoint.Y;
            double bz = (double)geom.BasePoint.Z;

            double maxSpan = 0.0;
            dynamic fedges = face.Edges;
            foreach (dynamic fe in fedges)
            {
                try
                {
                    string ct = ClassifyEdgeType(fe);
                    if (ct != "CIRCLE" && ct != "ELLIPSE") continue;

                    // Check if start == end vertex (closed loop = 360°)
                    try
                    {
                        dynamic sv = fe.StartVertex; dynamic ev = fe.StopVertex;
                        double dx=(double)sv.Point.X-(double)ev.Point.X;
                        double dy=(double)sv.Point.Y-(double)ev.Point.Y;
                        double dz=(double)sv.Point.Z-(double)ev.Point.Z;
                        if (Math.Sqrt(dx*dx+dy*dy+dz*dz) < 1e-6) return 360.0;
                    }
                    catch { }

                    // Project start and end onto plane perp to axis, measure angle
                    dynamic sv2 = fe.StartVertex; dynamic ev2 = fe.StopVertex;
                    double[] Project(double px, double py, double pz)
                    {
                        // vector from axis base to point
                        double rx=px-bx, ry=py-by, rz=pz-bz;
                        // subtract axis component
                        double dot = rx*ax+ry*ay+rz*az;
                        return [rx-dot*ax, ry-dot*ay, rz-dot*az];
                    }
                    var vs = Project((double)sv2.Point.X,(double)sv2.Point.Y,(double)sv2.Point.Z);
                    var ve = Project((double)ev2.Point.X,(double)ev2.Point.Y,(double)ev2.Point.Z);
                    double ls=Math.Sqrt(vs[0]*vs[0]+vs[1]*vs[1]+vs[2]*vs[2]);
                    double le=Math.Sqrt(ve[0]*ve[0]+ve[1]*ve[1]+ve[2]*ve[2]);
                    if (ls < 1e-10 || le < 1e-10) continue;
                    double cosA = (vs[0]*ve[0]+vs[1]*ve[1]+vs[2]*ve[2])/(ls*le);
                    cosA = Math.Max(-1.0, Math.Min(1.0, cosA));
                    double span = Math.Acos(cosA)*180.0/Math.PI;
                    if (span > maxSpan) maxSpan = span;
                }
                catch { }
            }
            return maxSpan > 0 ? maxSpan : (double?)null;
        }
        catch { return null; }
    }

    // 2. Convexity: "convex" if face normal points away from body centroid,
    //    "concave" if it points inward.  Uses face centroid + normal vs body bbox center.
    private static string FaceConvexity(string surfType, dynamic face, double[] bodyCenterXYZ)
    {
        try
        {
            var cen = FaceCentroid(face);
            var nor = FaceNormal(surfType, face);
            if (cen == null || nor == null) return "unknown";
            // vector from body center to face center
            double dx=cen[0]-bodyCenterXYZ[0], dy=cen[1]-bodyCenterXYZ[1], dz=cen[2]-bodyCenterXYZ[2];
            double dot = dx*nor[0]+dy*nor[1]+dz*nor[2];
            return dot >= 0 ? "convex" : "concave";
        }
        catch { return "unknown"; }
    }

    // 3. Cross-section from a face whose normal is approximately along a unit axis.
    //    Returns list of edges (index, curve_type, start, end, geometry) forming the outline.
    private static List<Dictionary<string,object?>>? FaceCrossSection(
        dynamic face, Dictionary<string,int> edgeIdxMap)
    {
        try
        {
            var edges = new List<Dictionary<string,object?>>();
            dynamic fedges = face.Edges;
            foreach (dynamic fe in fedges)
            {
                try
                {
                    string ct = ClassifyEdgeType(fe);
                    string? ek = EdgeKey(fe);
                    int eidx = ek != null && edgeIdxMap.TryGetValue(ek, out int tmp) ? tmp : -1;
                    double[]? sv2=null, ev2=null;
                    try { dynamic sv=fe.StartVertex; dynamic ev=fe.StopVertex;
                          sv2=[(double)sv.Point.X,(double)sv.Point.Y,(double)sv.Point.Z];
                          ev2=[(double)ev.Point.X,(double)ev.Point.Y,(double)ev.Point.Z]; } catch {}
                    var gp = EdgeGeoParams(ct, fe);
                    edges.Add(new Dictionary<string,object?>{
                        ["edge_id"]    = eidx >= 0 ? $"edge:{eidx}" : null,
                        ["curve_type"] = ct,
                        ["start"]      = sv2,
                        ["end"]        = ev2,
                        ["geometry"]   = gp.Count > 0 ? (object)gp : null
                    });
                }
                catch {}
            }
            return edges.Count > 0 ? edges : null;
        }
        catch { return null; }
    }

    // Returns true if the face normal is approximately parallel to a unit cardinal axis.
    private static bool IsEndFace(string surfType, dynamic face)
    {
        if (surfType != "PLANE") return false;
        try
        {
            double[]? n = FaceNormal(surfType, face);
            if (n == null) return false;
            // |dot with X| close to 1 → end face (perpendicular to length axis)
            return Math.Abs(n[0]) > 0.9;
        }
        catch { return false; }
    }

    /// <summary>
    /// Structured JSON summary of the active part geometry.
    /// Mirrors SimpleCADAPI inspect_step_rsummary.
    /// entity_id format: "face:N" / "edge:N" (zero-based, body-local).
    /// length_unit: cm (Inventor internal).
    /// </summary>
    public Dictionary<string, object?> GetModelJson(
        bool include_faces = true,
        bool include_edges = false,
        int  max_faces     = 64)
    {
        try
        {
            var compDef = ComponentDefinition();
            dynamic bodies = compDef.SurfaceBodies;
            int bodyCount  = (int)bodies.Count;

            var surfStats = new Dictionary<string, int>();
            var curvStats = new Dictionary<string, int>();
            var bodyList  = new List<Dictionary<string, object?>>();
            double totalVol = 0, totalArea = 0;
            double[]? mMin = null, mMax = null;

            for (int bi = 1; bi <= bodyCount; bi++)
            {
                dynamic body = ComDispatchHelper.WrapDispatch(bodies.Item(bi));
                double bVol = 0, bArea = 0;
                try { bVol = (double)compDef.MassProperties.Volume; } catch { }
                try { bArea = (double)body.Area; } catch { }
                totalVol  += bVol;
                totalArea += bArea;

                double[]? bMin = null, bMax = null;
                try
                {
                    dynamic box = body.RangeBox;
                    bMin = [(double)box.MinPoint.X, (double)box.MinPoint.Y, (double)box.MinPoint.Z];
                    bMax = [(double)box.MaxPoint.X, (double)box.MaxPoint.Y, (double)box.MaxPoint.Z];
                    if (mMin == null) { mMin = [bMin[0],bMin[1],bMin[2]]; mMax = [bMax[0],bMax[1],bMax[2]]; }
                    else { for (int k=0;k<3;k++) { if(bMin[k]<mMin[k])mMin[k]=bMin[k]; if(bMax[k]>mMax![k])mMax[k]=bMax[k]; } }
                }
                catch { }

                dynamic faces = body.Faces;
                int faceCount = (int)faces.Count;

                // stat pass — use face/edge directly (new helper signatures)
                for (int fi = 1; fi <= faceCount; fi++)
                {
                    try { dynamic f = ComDispatchHelper.WrapDispatch(faces.Item(fi)); string st = ClassifyFaceType(f); surfStats[st] = surfStats.GetValueOrDefault(st)+1; } catch { }
                }
                try
                {
                    dynamic bedges = body.Edges; int bec = (int)bedges.Count;
                    for (int ei=1;ei<=bec;ei++) { try { dynamic e = ComDispatchHelper.WrapDispatch(bedges.Item(ei)); string ct = ClassifyEdgeType(e); curvStats[ct]=curvStats.GetValueOrDefault(ct)+1; } catch { } }
                }
                catch { }

                // body center for convexity calculation
                double[] bodyCenter = bMin != null ? [(bMin[0]+bMax![0])/2,(bMin[1]+bMax[1])/2,(bMin[2]+bMax[2])/2] : [0.0,0.0,0.0];

                // Build full adjacency maps once per body
                BuildAdjacencyMaps(body, out Dictionary<string, int> edgeIdxMap, out Dictionary<string, List<int>> edgeFacesMap);

                // face detail
                var faceList = new List<Dictionary<string, object?>>();
                if (include_faces)
                {
                    int lim = Math.Min(faceCount, max_faces);
                    for (int fi = 1; fi <= lim; fi++)
                    {
                        try
                        {
                            dynamic face = ComDispatchHelper.WrapDispatch(faces.Item(fi));
                            string st = ClassifyFaceType(face);
                            var gp = FaceGeoParams(st, face);
                            double fa = GetFaceArea(st, face);
                            var aFaces = new List<string>(); var aEdges = new List<string>();
                            try
                            {
                                dynamic fe2 = face.Edges;
                                foreach (dynamic fe in fe2)
                                {
                                    try
                                    {
                                        string? ek = EdgeKey(fe);
                                        int eidx = -1;
                                        if (ek != null && edgeIdxMap.TryGetValue(ek, out eidx))
                                        {
                                            string eid = $"edge:{eidx}";
                                            if (!aEdges.Contains(eid)) aEdges.Add(eid);
                                            // neighboring faces = other faces sharing this edge
                                            if (edgeFacesMap.TryGetValue(ek, out var sharedFaces))
                                                foreach (int nf in sharedFaces)
                                                    if (nf != fi-1) { string nfid=$"face:{nf}"; if(!aFaces.Contains(nfid)) aFaces.Add(nfid); }
                                        }
                                    }
                                    catch { }
                                }
                            }
                            catch { }
                            faceList.Add(new Dictionary<string, object?>
                            {
                                ["entity_id"]        = $"face:{fi-1}",
                                ["surface_type"]     = st,
                                ["area"]             = fa,
                                ["centroid"]         = FaceCentroid(face),
                                ["normal_at_center"] = FaceNormal(st, face),
                                ["convexity"]        = FaceConvexity(st, face, bodyCenter),
                                ["arc_span_deg"]     = st == "CYLINDER" ? CylinderArcSpan(face) : null,
                                ["cross_section"]    = IsEndFace(st, face) ? (object?)FaceCrossSection(face, edgeIdxMap) : null,
                                ["geometry"]         = gp,
                                ["adjacency"]        = new Dictionary<string,object?>{["edges"]=aEdges,["neighboring_faces"]=aFaces.Distinct().ToList()}
                            });
                        }
                        catch { }
                    }
                }

                // edge detail
                var edgeList = new List<Dictionary<string, object?>>();
                if (include_edges)
                {
                    try
                    {
                        dynamic bedges = body.Edges; int bec = (int)bedges.Count;
                        for (int ei=1;ei<=bec;ei++)
                        {
                            try
                            {
                                dynamic edge = ComDispatchHelper.WrapDispatch(bedges.Item(ei));
                                string ct = ClassifyEdgeType(edge);
                                var cp = EdgeGeoParams(ct, edge);
                                double el = GetEdgeLength(ct, edge);
                                double[]? es=null,ee=null;
                                try{dynamic sv=edge.StartVertex;dynamic ev=edge.StopVertex;es=[(double)sv.Point.X,(double)sv.Point.Y,(double)sv.Point.Z];ee=[(double)ev.Point.X,(double)ev.Point.Y,(double)ev.Point.Z];}catch{}
                                edgeList.Add(new Dictionary<string,object?>{["entity_id"]=$"edge:{ei-1}",["curve_type"]=ct,["length"]=el,["start"]=es,["end"]=ee,["geometry"]=cp});
                            }
                            catch { }
                        }
                    }
                    catch { }
                }

                int ec2=0,vc=0; try{ec2=(int)body.Edges.Count;}catch{} try{vc=(int)body.Vertices.Count;}catch{}
                var bbox = bMin!=null ? (object)new Dictionary<string,object?>{["min"]=bMin,["max"]=bMax,["size"]=new double[]{bMax![0]-bMin[0],bMax[1]-bMin[1],bMax[2]-bMin[2]},["center"]=new double[]{(bMin[0]+bMax[0])/2,(bMin[1]+bMax[1])/2,(bMin[2]+bMax[2])/2}} : null;
                bodyList.Add(new Dictionary<string,object?>{["entity_id"]=$"body:{bi-1}",["volume"]=bVol,["surface_area"]=bArea,["face_count"]=faceCount,["edge_count"]=ec2,["vertex_count"]=vc,["bounding_box"]=bbox,["faces"]=faceList.Count>0?(object)faceList:null,["edges"]=edgeList.Count>0?(object)edgeList:null});
            }

            var mSize = mMin!=null ? new double[]{mMax![0]-mMin[0],mMax[1]-mMin[1],mMax[2]-mMin[2]} : null;
            return new Dictionary<string, object?>
            {
                ["success"]                 = true,
                ["length_unit"]             = "cm",
                ["body_count"]              = bodyCount,
                ["total_volume"]            = totalVol,
                ["total_surface_area"]      = totalArea,
                ["bounding_box"]            = mMin!=null ? (object)new Dictionary<string,object?>{["min"]=mMin,["max"]=mMax,["size"]=mSize,["center"]=new double[]{(mMin[0]+mMax![0])/2,(mMin[1]+mMax[1])/2,(mMin[2]+mMax[2])/2}} : null,
                ["surface_type_statistics"] = surfStats,
                ["curve_type_statistics"]   = curvStats,
                ["bodies"]                  = bodyList,
                ["note"]                    = include_faces
                    ? $"Faces capped at {max_faces} per body. Pass include_edges=true for edge geometry."
                    : "Face details omitted. Pass include_faces=true to include them."
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"GetModelJson failed: {ex.Message}", ex); }
    }

    // ── GetEntityDetail ───────────────────────────────────────────────

    /// <summary>
    /// Full geometry detail for one face or edge.
    /// entity_id: "face:N" or "edge:N" (zero-based, body-local).
    /// body_index: 0-based body selector for multi-body parts.
    /// Mirrors SimpleCADAPI inspect_step_entity_rdescriptor.
    /// </summary>
    public Dictionary<string, object?> GetEntityDetail(string entity_id, int body_index = 0)
    {
        try
        {
            var compDef = ComponentDefinition();
            dynamic bodies = compDef.SurfaceBodies;
            int bodyCount = (int)bodies.Count;
            if (body_index < 0 || body_index >= bodyCount)
                return ErrorResult.Create($"body_index {body_index} out of range (0..{bodyCount-1}).");

            dynamic body = ComDispatchHelper.WrapDispatch(bodies.Item(body_index + 1));
            var parts = entity_id.Split(':');
            if (parts.Length != 2 || !int.TryParse(parts[1], out int zeroIdx))
                return ErrorResult.Create("entity_id must be 'face:N' or 'edge:N' (zero-based).");

            string kind = parts[0].ToLowerInvariant();
            int oneIdx = zeroIdx + 1;

            // Build adjacency maps once, shared by both face and edge branches
            BuildAdjacencyMaps(body, out Dictionary<string, int> adjEdgeIdx, out Dictionary<string, List<int>> adjEdgeFaces);

            if (kind == "face")
            {
                dynamic faces = body.Faces;
                int fc = (int)faces.Count;
                if (zeroIdx < 0 || zeroIdx >= fc)
                    return ErrorResult.Create($"face:{zeroIdx} out of range (0..{fc-1}).");

                dynamic face = ComDispatchHelper.WrapDispatch(faces.Item(oneIdx));
                string st = ClassifyFaceType(face);
                var gp = FaceGeoParams(st, face);
                double fa = GetFaceArea(st, face);

                // uv range from RangeBox (avoids SurfaceEvaluator double-param issues)
                double[]? uvRange = GetUVRange(face);

                // normal samples: use geometry-based normal (no SurfaceEvaluator)
                var normalSamples = new List<object?>();
                try
                {
                    double[]? n1 = FaceNormal(st, face);
                    if (n1 != null) { normalSamples.Add(n1); }
                }
                catch { }

                var edgeIdxMap2 = adjEdgeIdx;
                var edgeFacesMap2 = adjEdgeFaces;
                var aFaces = new List<string>(); var aEdges = new List<string>();
                try
                {
                    dynamic fe2 = face.Edges;
                    foreach (dynamic fe in fe2)
                    {
                        try
                        {
                            string? ek = EdgeKey(fe);
                            int eidx2 = -1;
                            if (ek != null && edgeIdxMap2.TryGetValue(ek, out eidx2))
                            {
                                string eid = $"edge:{eidx2}";
                                if (!aEdges.Contains(eid)) aEdges.Add(eid);
                                if (edgeFacesMap2.TryGetValue(ek, out var sharedF))
                                    foreach (int nf in sharedF)
                                        if (nf != zeroIdx) { string nfid=$"face:{nf}"; if(!aFaces.Contains(nfid)) aFaces.Add(nfid); }
                            }
                        }
                        catch { }
                    }
                }
                catch { }

                double[]? fbox = FaceRangeBox(face);

                return new Dictionary<string, object?>
                {
                    ["success"]          = true,
                    ["entity_id"]        = $"face:{zeroIdx}",
                    ["kind"]             = "face",
                    ["body_index"]       = body_index,
                    ["surface_type"]     = st,
                    ["area"]             = fa,
                    ["centroid"]         = FaceCentroid(face),
                    ["normal_at_center"] = FaceNormal(st, face),
                    ["convexity"]        = FaceConvexity(st, face, new double[]{0,0,0}),
                    ["arc_span_deg"]     = st == "CYLINDER" ? CylinderArcSpan(face) : null,
                    ["cross_section"]    = IsEndFace(st, face) ? (object?)FaceCrossSection(face, adjEdgeIdx) : null,
                    ["normal_samples"]   = normalSamples.Count > 0 ? (object)normalSamples : null,
                    ["uv_range"]         = uvRange,
                    ["geometry"]         = gp,
                    ["bounding_box"]     = fbox,
                    ["adjacency"]        = new Dictionary<string,object?>{["edges"]=aEdges,["neighboring_faces"]=aFaces.Distinct().ToList()}
                };
            }
            else if (kind == "edge")
            {
                dynamic edges = body.Edges;
                int ec = (int)edges.Count;
                if (zeroIdx < 0 || zeroIdx >= ec)
                    return ErrorResult.Create($"edge:{zeroIdx} out of range (0..{ec-1}).");

                dynamic edge = ComDispatchHelper.WrapDispatch(edges.Item(oneIdx));
                string ct = ClassifyEdgeType(edge);
                var cp = EdgeGeoParams(ct, edge);
                double el = GetEdgeLength(ct, edge);

                double[]? es = null, ee = null;
                try { dynamic sv=edge.StartVertex; dynamic ev=edge.StopVertex; es=[(double)sv.Point.X,(double)sv.Point.Y,(double)sv.Point.Z]; ee=[(double)ev.Point.X,(double)ev.Point.Y,(double)ev.Point.Z]; } catch { }

                string? ekey = EdgeKey(edge);
                var adjF = new List<string>();
                if (ekey != null && adjEdgeFaces.TryGetValue(ekey, out var adjFaceIdxs))
                    foreach (int fi in adjFaceIdxs) adjF.Add($"face:{fi}");

                return new Dictionary<string, object?>
                {
                    ["success"]    = true,
                    ["entity_id"]  = $"edge:{zeroIdx}",
                    ["kind"]       = "edge",
                    ["body_index"] = body_index,
                    ["curve_type"] = ct,
                    ["length"]     = el,
                    ["start"]      = es,
                    ["end"]        = ee,
                    ["geometry"]   = cp,
                    ["adjacency"]  = new Dictionary<string,object?>{["faces"]=adjF}
                };
            }
            else
            {
                return ErrorResult.Create("entity_id kind must be 'face' or 'edge'.");
            }
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"GetEntityDetail failed: {ex.Message}", ex); }
    }
}