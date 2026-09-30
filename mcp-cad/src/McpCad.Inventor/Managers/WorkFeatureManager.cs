using McpCad.Core.Exceptions;
using McpCad.Core.Models;
using McpCad.Inventor.Helpers;
using InvApp = Inventor.Application;

namespace McpCad.Inventor.Managers;

/// <summary>
/// Manages work feature operations: work planes, work axes, and work points.
/// Uses InventorDriver for COM connection and ComDispatchHelper for dynamic dispatch
/// to Inventor's WorkPlanes, WorkAxes, and WorkPoints COM collections.
/// </summary>
public class WorkFeatureManager
{
    private readonly InventorDriver _driver;

    public WorkFeatureManager(InventorDriver driver) => _driver = driver;

    // ── Internal guards ───────────────────────────────────────────────

    private InvApp App => _driver.InventorApp;

    private dynamic ComponentDefinition()
    {
        var compDef = _driver.ComponentDefinition
            ?? throw new InventorComException("No component definition available. Open or create a part document first.");
        return ComDispatchHelper.WrapDispatch(compDef);
    }

    // ── Public API: WorkPlane ─────────────────────────────────────────

    /// <summary>
    /// Create or retrieve a work plane.
    /// Supported definitions:
    ///   default            — get built-in plane by index (1=XY, 2=XZ, 3=YZ)
    ///   offset_from_plane  — create plane parallel to an existing plane at offset distance
    ///   through_three_points — create plane through three points
    ///   normal_to_curve    — create plane normal to a curve (edge) at a point
    /// </summary>
    public Dictionary<string, object?> WorkPlane(string definition, string reference1, string reference2, double offset)
    {
        try
        {
            var compDef = ComponentDefinition();

            switch (definition.ToLowerInvariant())
            {
                case "default":
                    return CreateDefaultPlane(compDef, reference1);

                case "offset_from_plane":
                    return CreateOffsetPlane(compDef, reference1, offset);

                case "through_three_points":
                    return CreatePlaneThreePoints(compDef, reference1, reference2);

                case "normal_to_curve":
                    return CreatePlaneNormalToCurve(compDef, reference1, reference2);

                default:
                    return ErrorResult.Create(
                        $"Unknown work plane definition '{definition}'. " +
                        "Supported: default, offset_from_plane, through_three_points, normal_to_curve.");
            }
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex)
        {
            throw new InventorComException($"Failed to create work plane: {ex.Message}", ex);
        }
    }

    // ── Public API: WorkAxis ──────────────────────────────────────────

    /// <summary>
    /// Create or retrieve a work axis.
    /// Supported definitions:
    ///   default             — get built-in axis by index (1=X, 2=Y, 3=Z)
    ///   through_two_points  — create axis through two points
    ///   normal_to_plane     — create axis normal to a plane through a point
    ///   along_edge          — create axis along an existing edge
    /// </summary>
    public Dictionary<string, object?> WorkAxis(string definition, string reference1, string reference2)
    {
        try
        {
            var compDef = ComponentDefinition();

            switch (definition.ToLowerInvariant())
            {
                case "default":
                    return CreateDefaultAxis(compDef, reference1);

                case "through_two_points":
                    return CreateAxisTwoPoints(compDef, reference1, reference2);

                case "normal_to_plane":
                    return CreateAxisNormalToPlane(compDef, reference1, reference2);

                case "along_edge":
                    return CreateAxisAlongEdge(compDef, reference1);

                default:
                    return ErrorResult.Create(
                        $"Unknown work axis definition '{definition}'. " +
                        "Supported: default, through_two_points, normal_to_plane, along_edge.");
            }
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex)
        {
            throw new InventorComException($"Failed to create work axis: {ex.Message}", ex);
        }
    }

    // ── Public API: WorkPoint ─────────────────────────────────────────

    /// <summary>
    /// Create or retrieve a work point.
    /// Supported definitions:
    ///   default         — get built-in work point by index
    ///   at_coordinates  — create point at X, Y, Z coordinates
    ///   on_curve        — create point on a curve at a parameter
    ///   intersection    — create point at intersection of two entities
    /// </summary>
    public Dictionary<string, object?> WorkPoint(string definition, string reference1, string reference2, string reference3)
    {
        try
        {
            var compDef = ComponentDefinition();

            switch (definition.ToLowerInvariant())
            {
                case "default":
                    return CreateDefaultPoint(compDef, reference1);

                case "at_coordinates":
                    return CreatePointAtCoords(compDef, reference1, reference2, reference3);

                case "on_curve":
                    return CreatePointOnCurve(compDef, reference1, reference2);

                case "intersection":
                    return CreatePointIntersection(compDef, reference1, reference2);

                default:
                    return ErrorResult.Create(
                        $"Unknown work point definition '{definition}'. " +
                        "Supported: default, at_coordinates, on_curve, intersection.");
            }
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex)
        {
            throw new InventorComException($"Failed to create work point: {ex.Message}", ex);
        }
    }

    // ── WorkPlane implementations ─────────────────────────────────────

    private Dictionary<string, object?> CreateDefaultPlane(dynamic compDef, string ref1)
    {
        if (!int.TryParse(ref1, out int index) || index < 1 || index > 3)
            return ErrorResult.Create($"Invalid work plane index '{ref1}'. Valid indices: 1 (XY), 2 (XZ), 3 (YZ).");

        dynamic plane = compDef.WorkPlanes.Item(index);

        string[] planeNames = ["", "XY Plane", "XZ Plane", "YZ Plane"];
        double[][] origins = [[], [0, 0, 0], [0, 0, 0], [0, 0, 0]];
        double[][] normals = [[], [0, 0, 1], [0, 1, 0], [1, 0, 0]];
        double[][] uDirs = [[], [1, 0, 0], [1, 0, 0], [0, 1, 0]];
        double[][] vDirs = [[], [0, 1, 0], [0, 0, 1], [0, 0, 1]];
        return new Dictionary<string, object?>
        {
            ["success"] = true,
            ["plane"] = new Dictionary<string, object?>
            {
                ["name"] = planeNames[index],
                ["id"] = index,
                ["origin"] = origins[index],
                ["normal"] = normals[index],
                ["u"] = uDirs[index],
                ["v"] = vDirs[index],
            },
        };
    }

    private Dictionary<string, object?> CreateOffsetPlane(dynamic compDef, string planeRef, double offset)
    {
        if (string.IsNullOrWhiteSpace(planeRef))
            return ErrorResult.Create("Missing required parameter: reference plane for offset_from_plane.");

        dynamic plane = ResolveGeometryReference(compDef, planeRef, "plane");
        dynamic workPlane = compDef.WorkPlanes.AddByPlaneAndOffset(plane, offset);

        // Report the plane's ACTUAL world placement so the caller can verify the
        // plane landed where intended (e.g. tangent to a segment's top) instead
        // of guessing. point_on_plane = the plane origin projected into world;
        // normal = plane facing. For offset_from_plane('XY', 1.5) this comes back
        // as point (0,0,1.5), normal (0,0,1).
        double[]? pointOnPlane = null, planeNormal = null, u = null, v = null;
        try
        {
            dynamic pg = workPlane.Plane;      // Plane geometry
            dynamic rp = pg.RootPoint;         // Point3d on the plane
            dynamic nm = pg.Normal;            // UnitVector
            pointOnPlane = [(double)rp.X, (double)rp.Y, (double)rp.Z];
            planeNormal = [(double)nm.X, (double)nm.Y, (double)nm.Z];
            if (Math.Abs(planeNormal[2]) > 0.999) { u = [1, 0, 0]; v = [0, Math.Sign(planeNormal[2]), 0]; }
            else if (Math.Abs(planeNormal[1]) > 0.999) { u = [1, 0, 0]; v = [0, 0, -Math.Sign(planeNormal[1])]; }
            else if (Math.Abs(planeNormal[0]) > 0.999) { u = [0, 1, 0]; v = [0, 0, Math.Sign(planeNormal[0])]; }
        }
        catch { pointOnPlane = null; planeNormal = null; }
        if (pointOnPlane is null || planeNormal is null || u is null || v is null)
            return ErrorResult.Create("Could not determine a deterministic numeric frame for the offset plane.");

        return new Dictionary<string, object?>
        {
            ["success"] = true,
            ["plane"] = new Dictionary<string, object?>
            {
                ["name"] = workPlane.Name as string,
                ["id"] = workPlane.Name as string,
                ["offset"] = offset,
                ["reference_plane"] = planeRef,
                ["origin"] = pointOnPlane,
                ["normal"] = planeNormal,
                ["u"] = u,
                ["v"] = v,
            },
        };
    }

    private Dictionary<string, object?> CreatePlaneThreePoints(dynamic compDef, string ref1, string ref2)
    {
        // Parse point references: ref1 = point1, ref2 = point2, need third point.
        // Convention: ref2 contains two point identifiers separated by comma.
        string[] parts = ref2.Split(',', 2, StringSplitOptions.TrimEntries);
        string pointRef1 = ref1;
        string pointRef2 = parts[0];
        string pointRef3 = parts.Length > 1 ? parts[1] : "";

        if (string.IsNullOrWhiteSpace(pointRef3))
            return ErrorResult.Create("Missing third point reference for through_three_points. " +
                "Use: reference1=point1, reference2=point2,point3");

        dynamic p1 = ResolveGeometryReference(compDef, pointRef1, "point");
        dynamic p2 = ResolveGeometryReference(compDef, pointRef2, "point");
        dynamic p3 = ResolveGeometryReference(compDef, pointRef3, "point");

        dynamic workPlane = compDef.WorkPlanes.AddByThreePoints(p1, p2, p3);

        return new Dictionary<string, object?>
        {
            ["success"] = true,
            ["plane"] = new Dictionary<string, object?>
            {
                ["name"] = workPlane.Name as string,
                ["id"] = workPlane.Name as string,
            },
        };
    }

    private Dictionary<string, object?> CreatePlaneNormalToCurve(dynamic compDef, string curveRef, string pointRef)
    {
        if (string.IsNullOrWhiteSpace(curveRef))
            return ErrorResult.Create("Missing required parameter: curve reference for normal_to_curve.");

        dynamic curve = ResolveGeometryReference(compDef, curveRef, "edge");

        // If pointRef provided, resolve it; otherwise use the curve's midpoint
        dynamic point;
        if (!string.IsNullOrWhiteSpace(pointRef))
        {
            point = ResolveGeometryReference(compDef, pointRef, "point");
        }
        else
        {
            // Default: use midpoint of the edge
            dynamic midpoint = ComDispatchHelper.WrapDispatch(curve.Geometry?.MidPoint ?? curve.StartVertex?.Point);
            if (midpoint is null)
                return ErrorResult.Create("Cannot determine a point on the curve for normal_to_curve. Provide a point reference.");
            point = midpoint;
        }

        dynamic workPlane = compDef.WorkPlanes.AddByNormalToCurve(curve, point);

        return new Dictionary<string, object?>
        {
            ["success"] = true,
            ["plane"] = new Dictionary<string, object?>
            {
                ["name"] = workPlane.Name as string,
                ["id"] = workPlane.Name as string,
            },
        };
    }

    // ── WorkAxis implementations ──────────────────────────────────────

    private Dictionary<string, object?> CreateDefaultAxis(dynamic compDef, string ref1)
    {
        if (!int.TryParse(ref1, out int index) || index < 1 || index > 3)
            return ErrorResult.Create($"Invalid work axis index '{ref1}'. Valid indices: 1 (X), 2 (Y), 3 (Z).");

        dynamic axis = compDef.WorkAxes.Item(index);

        string[] axisNames = ["", "X Axis", "Y Axis", "Z Axis"];
        return new Dictionary<string, object?>
        {
            ["success"] = true,
            ["axis"] = new Dictionary<string, object?>
            {
                ["name"] = axisNames[index],
                ["id"] = index,
            },
        };
    }

    private Dictionary<string, object?> CreateAxisTwoPoints(dynamic compDef, string pointRef1, string pointRef2)
    {
        if (string.IsNullOrWhiteSpace(pointRef1) || string.IsNullOrWhiteSpace(pointRef2))
            return ErrorResult.Create("Missing required parameter(s) for through_two_points. Provide both point references.");

        dynamic p1 = ResolveGeometryReference(compDef, pointRef1, "point");
        dynamic p2 = ResolveGeometryReference(compDef, pointRef2, "point");

        dynamic workAxis = compDef.WorkAxes.AddByTwoPoints(p1, p2);

        return new Dictionary<string, object?>
        {
            ["success"] = true,
            ["axis"] = new Dictionary<string, object?>
            {
                ["name"] = workAxis.Name as string,
                ["id"] = workAxis.Name as string,
            },
        };
    }

    private Dictionary<string, object?> CreateAxisNormalToPlane(dynamic compDef, string planeRef, string pointRef)
    {
        if (string.IsNullOrWhiteSpace(planeRef))
            return ErrorResult.Create("Missing required parameter: plane reference for normal_to_plane.");

        dynamic plane = ResolveGeometryReference(compDef, planeRef, "plane");

        dynamic point;
        if (!string.IsNullOrWhiteSpace(pointRef))
        {
            point = ResolveGeometryReference(compDef, pointRef, "point");
        }
        else
        {
            // Default: center point (WorkPoint, valid for AddByNormalToSurface)
            point = compDef.WorkPoints.Item(1);
        }

        dynamic workAxis = compDef.WorkAxes.AddByNormalToSurface(plane, point);

        return new Dictionary<string, object?>
        {
            ["success"] = true,
            ["axis"] = new Dictionary<string, object?>
            {
                ["name"] = workAxis.Name as string,
                ["id"] = workAxis.Name as string,
            },
        };
    }

    private Dictionary<string, object?> CreateAxisAlongEdge(dynamic compDef, string edgeRef)
    {
        if (string.IsNullOrWhiteSpace(edgeRef))
            return ErrorResult.Create("Missing required parameter: edge reference for along_edge.");

        dynamic edge = ResolveGeometryReference(compDef, edgeRef, "edge");
        dynamic workAxis = compDef.WorkAxes.AddByLine(edge);

        return new Dictionary<string, object?>
        {
            ["success"] = true,
            ["axis"] = new Dictionary<string, object?>
            {
                ["name"] = workAxis.Name as string,
                ["id"] = workAxis.Name as string,
            },
        };
    }

    // ── WorkPoint implementations ─────────────────────────────────────

    private Dictionary<string, object?> CreateDefaultPoint(dynamic compDef, string ref1)
    {
        if (!int.TryParse(ref1, out int index) || index < 1)
            return ErrorResult.Create($"Invalid work point index '{ref1}'.");

        dynamic point = compDef.WorkPoints.Item(index);

        return new Dictionary<string, object?>
        {
            ["success"] = true,
            ["point"] = new Dictionary<string, object?>
            {
                ["name"] = point.Name as string,
                ["id"] = index,
            },
        };
    }

    private Dictionary<string, object?> CreatePointAtCoords(dynamic compDef, string xRef, string yRef, string zRef)
    {
        if (!double.TryParse(xRef, out double x))
            return ErrorResult.Create($"Invalid X coordinate '{xRef}'.");
        if (!double.TryParse(yRef, out double y))
            return ErrorResult.Create($"Invalid Y coordinate '{yRef}'.");
        if (!double.TryParse(zRef, out double z))
            return ErrorResult.Create("Missing required parameter: z coordinate for at_coordinates.");

        dynamic transientGeom = App.TransientGeometry;
        dynamic pt = transientGeom.CreatePoint(x, y, z);
        dynamic workPoint = compDef.WorkPoints.AddFixed(pt);

        return new Dictionary<string, object?>
        {
            ["success"] = true,
            ["point"] = new Dictionary<string, object?>
            {
                ["x"] = x,
                ["y"] = y,
                ["z"] = z,
                ["name"] = workPoint.Name as string,
                ["id"] = workPoint.Name as string,
            },
        };
    }

    private Dictionary<string, object?> CreatePointOnCurve(dynamic compDef, string curveRef, string paramRef)
    {
        if (string.IsNullOrWhiteSpace(curveRef))
            return ErrorResult.Create("Missing required parameter: curve reference for on_curve.");

        dynamic curve = ResolveGeometryReference(compDef, curveRef, "edge");

        // paramRef: parameter along the curve (0.0 to 1.0) or a point reference
        if (!string.IsNullOrWhiteSpace(paramRef) && double.TryParse(paramRef, out double param))
        {
            // Use parameter along curve (0.0 to 1.0)
            dynamic geom = curve.Geometry;
            if (geom is null)
                return ErrorResult.Create("Curve has no accessible geometry for parameter evaluation.");

            dynamic evalPoint;
            try
            {
                // Try Evaluator for parameter-based point
                dynamic evaluator = geom.Evaluator;
                double[] pointData = new double[3];
                evaluator.GetPointAtParam(new double[] { param }, ref pointData[0], ref pointData[1], ref pointData[2]);
                evalPoint = App.TransientGeometry.CreatePoint(pointData[0], pointData[1], pointData[2]);
            }
            catch
            {
                return ErrorResult.Create($"Failed to evaluate curve at parameter {param}.");
            }

            dynamic workPoint = compDef.WorkPoints.AddFixed(evalPoint);
            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["point"] = new Dictionary<string, object?>
                {
                    ["name"] = workPoint.Name as string,
                    ["id"] = workPoint.Name as string,
                    ["parameter"] = param,
                },
            };
        }

        // Otherwise: resolve as a point reference for proximity-based placement
        dynamic refPoint = ResolveGeometryReference(compDef, paramRef, "point");
        dynamic wpClosest = compDef.WorkPoints.AddByCurveAndEntity(curve, refPoint);

        return new Dictionary<string, object?>
        {
            ["success"] = true,
            ["point"] = new Dictionary<string, object?>
            {
                ["name"] = wpClosest.Name as string,
                ["id"] = wpClosest.Name as string,
            },
        };
    }

    private Dictionary<string, object?> CreatePointIntersection(dynamic compDef, string entityRef1, string entityRef2)
    {
        if (string.IsNullOrWhiteSpace(entityRef1) || string.IsNullOrWhiteSpace(entityRef2))
            return ErrorResult.Create("Missing required parameter(s) for intersection. Provide two entity references.");

        dynamic e1 = ResolveGeometryReference(compDef, entityRef1, "entity");
        dynamic e2 = ResolveGeometryReference(compDef, entityRef2, "entity");

        dynamic workPoint = compDef.WorkPoints.AddByTwoEntities(e1, e2);

        return new Dictionary<string, object?>
        {
            ["success"] = true,
            ["point"] = new Dictionary<string, object?>
            {
                ["name"] = workPoint.Name as string,
                ["id"] = workPoint.Name as string,
            },
        };
    }

    // ── Geometry Reference Resolution ─────────────────────────────────

    /// <summary>
    /// Resolve a geometry reference string to a COM object.
    /// Supports:
    ///   - Plane names: "XY Plane", "XZ Plane", "YZ Plane", "1", "2", "3"
    ///   - Axis names: "X Axis", "Y Axis", "Z Axis", "1", "2", "3"
    ///   - Point indices: "1", "2", etc. from WorkPoints collection
    ///   - Edge indices: "e1", "e2", etc.
    /// The hint parameter guides priority when ambiguous.
    /// </summary>
    private dynamic ResolveGeometryReference(dynamic compDef, string reference, string hint)
    {
        if (string.IsNullOrWhiteSpace(reference))
            throw new InventorComException($"Missing geometry reference for {hint}.");

        string lower = reference.ToLowerInvariant().Trim();

        // ── Plane references ──────────────────────────────────────────
        if (hint == "plane" || lower.Contains("plane"))
        {
            var planeMap = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
            {
                ["xy plane"] = 1, ["xy"] = 1, ["1"] = 1,
                ["xz plane"] = 2, ["xz"] = 2, ["2"] = 2,
                ["yz plane"] = 3, ["yz"] = 3, ["3"] = 3,
            };

            if (planeMap.TryGetValue(lower, out int idx))
                return compDef.WorkPlanes.Item(idx);

            // Try as numeric index
            if (int.TryParse(reference, out int planeIdx) && planeIdx >= 1)
                return compDef.WorkPlanes.Item(planeIdx);

            // Try by name
            try
            {
                return compDef.WorkPlanes.Item(reference);
            }
            catch { /* fall through */ }

            throw new InventorComException($"Could not resolve plane reference '{reference}'.");
        }

        // ── Axis references ───────────────────────────────────────────
        if (hint == "axis" || lower.Contains("axis"))
        {
            var axisMap = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
            {
                ["x axis"] = 1, ["x"] = 1, ["1"] = 1,
                ["y axis"] = 2, ["y"] = 2, ["2"] = 2,
                ["z axis"] = 3, ["z"] = 3, ["3"] = 3,
            };

            if (axisMap.TryGetValue(lower, out int idx))
                return compDef.WorkAxes.Item(idx);

            if (int.TryParse(reference, out int axisIdx) && axisIdx >= 1)
                return compDef.WorkAxes.Item(axisIdx);

            try
            {
                return compDef.WorkAxes.Item(reference);
            }
            catch { /* fall through */ }

            throw new InventorComException($"Could not resolve axis reference '{reference}'.");
        }

        // ── Point references ──────────────────────────────────────────
        if (hint == "point")
        {
            if (int.TryParse(reference, out int ptIdx) && ptIdx >= 1)
            {
                try
                {
                    return compDef.WorkPoints.Item(ptIdx);
                }
                catch { /* fall through */ }
            }

            // Try as sketch point index
            try
            {
                var sketches = compDef.Sketches;
                if (sketches.Count > 0)
                {
                    dynamic sketch = sketches.Item(sketches.Count);
                    if (int.TryParse(reference, out ptIdx) && ptIdx >= 1)
                        return sketch.SketchPoints.Item(ptIdx);
                }
            }
            catch { /* fall through */ }

            throw new InventorComException($"Could not resolve point reference '{reference}'.");
        }

        // ── Edge references ───────────────────────────────────────────
        if (hint == "edge")
        {
            string edgeIdx = lower.StartsWith("e") ? lower[1..] : lower;
            if (int.TryParse(edgeIdx, out int eIdx) && eIdx >= 1)
            {
                try
                {
                    dynamic surfaceBody = ComDispatchHelper.WrapDispatch(compDef.SurfaceBodies.Item(1));
                    return surfaceBody.Edges.Item(eIdx);
                }
                catch
                {
                    throw new InventorComException($"Edge index {eIdx} not found on the active body.");
                }
            }

            throw new InventorComException($"Invalid edge reference '{reference}'. Use 'e1', 'e2', etc.");
        }

        // ── Generic entity (try multiple collections) ─────────────────
        if (hint == "entity")
        {
            // Try as edge first
            try { return ResolveGeometryReference(compDef, reference, "edge"); } catch { }
            // Try as plane
            try { return ResolveGeometryReference(compDef, reference, "plane"); } catch { }
            // Try as axis
            try { return ResolveGeometryReference(compDef, reference, "axis"); } catch { }
            // Try as point
            try { return ResolveGeometryReference(compDef, reference, "point"); } catch { }

            throw new InventorComException($"Could not resolve entity reference '{reference}'.");
        }

        // ── Fallback: try each known collection ───────────────────────
        try { return ResolveGeometryReference(compDef, reference, "plane"); } catch { }
        try { return ResolveGeometryReference(compDef, reference, "axis"); } catch { }
        try { return ResolveGeometryReference(compDef, reference, "point"); } catch { }
        try { return ResolveGeometryReference(compDef, reference, "edge"); } catch { }

        throw new InventorComException($"Could not resolve geometry reference '{reference}' (hint: {hint}).");
    }
}
