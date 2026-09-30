using McpCad.Core;

namespace McpCad.Tests.Mocks;

/// <summary>
/// Mock implementation of IMechanicalCadProvider that returns canned success results.
/// Use <see cref="WithError"/> to create a provider where every method returns errors,
/// or set individual method responses via <c>SetXxxResult</c> for fine-grained control.
/// </summary>
public class MockInventorProvider : IMechanicalCadProvider
{
    // ── Per-method overrides (null = use default success response) ──

    private Dictionary<string, object?>? _connectResult;
    private Dictionary<string, object?>? _disconnectResult;
    private Dictionary<string, object?>? _healthResult;
    private Dictionary<string, object?>? _docOpenResult;
    private Dictionary<string, object?>? _docNewPartResult;
    private Dictionary<string, object?>? _docNewAssemblyResult;
    private Dictionary<string, object?>? _docSaveResult;
    private Dictionary<string, object?>? _docSaveAsResult;
    private Dictionary<string, object?>? _docCloseResult;
    private Dictionary<string, object?>? _sketchCreateResult;
    private Dictionary<string, object?>? _sketchLineResult;
    private Dictionary<string, object?>? _sketchCircleResult;
    private Dictionary<string, object?>? _sketchArcResult;
    private Dictionary<string, object?>? _sketchRectangleResult;
    private Dictionary<string, object?>? _sketchDimensionResult;
    private Dictionary<string, object?>? _sketchPointResult;
    private Dictionary<string, object?>? _sketchSplineResult;
    private Dictionary<string, object?>? _sketchEllipseResult;
    private Dictionary<string, object?>? _sketchCircularPatternResult;
    private Dictionary<string, object?>? _sketchRectangularPatternResult;
    private Dictionary<string, object?>? _sketchOffsetResult;
    private Dictionary<string, object?>? _sketchMoveResult;
    private Dictionary<string, object?>? _sketchRotateResult;
    private Dictionary<string, object?>? _sketchDeleteResult;
    private Dictionary<string, object?>? _sketchConstraintResult;
    private Dictionary<string, object?>? _sketchTrimResult;
    private Dictionary<string, object?>? _sketchScaleResult;
    private Dictionary<string, object?>? _sketchMirrorResult;
    private Dictionary<string, object?>? _sketchLineCloseResult;
    private Dictionary<string, object?>? _sketchProfilesResult;
    private Dictionary<string, object?>? _extrudeResult;
    private Dictionary<string, object?>? _revolveResult;
    private Dictionary<string, object?>? _sweepResult;
    private Dictionary<string, object?>? _filletResult;
    private Dictionary<string, object?>? _chamferResult;
    private Dictionary<string, object?>? _circularPatternResult;
    private Dictionary<string, object?>? _mirrorFeatureResult;
    private Dictionary<string, object?>? _rectangularPatternResult;
    private Dictionary<string, object?>? _loftResult;
    private Dictionary<string, object?>? _coilResult;
    private Dictionary<string, object?>? _ribResult;
    private Dictionary<string, object?>? _embossResult;
    private Dictionary<string, object?>? _deriveResult;
    private Dictionary<string, object?>? _holeResult;
    private Dictionary<string, object?>? _threadResult;
    private Dictionary<string, object?>? _inspectEdgesResult;
    private Dictionary<string, object?>? _paramListResult;
    private Dictionary<string, object?>? _paramGetResult;
    private Dictionary<string, object?>? _paramSetResult;
    private Dictionary<string, object?>? _paramSetExpressionResult;
    private Dictionary<string, object?>? _iPropertyGetResult;
    private Dictionary<string, object?>? _iPropertySetResult;
    private Dictionary<string, object?>? _iPropertySummaryResult;
    private Dictionary<string, object?>? _iPropertyCustomGetResult;
    private Dictionary<string, object?>? _iPropertyCustomSetResult;
    private Dictionary<string, object?>? _exportStepResult;
    private Dictionary<string, object?>? _exportStlResult;
    private Dictionary<string, object?>? _exportPdfResult;
    private Dictionary<string, object?>? _exportDxfResult;
    private Dictionary<string, object?>? _workPlaneResult;
    private Dictionary<string, object?>? _workAxisResult;
    private Dictionary<string, object?>? _workPointResult;
    private Dictionary<string, object?>? _shellResult;
    private Dictionary<string, object?>? _draftResult;
    private Dictionary<string, object?>? _splitResult;
    private Dictionary<string, object?>? _combineResult;
    private Dictionary<string, object?>? _thickenResult;

    /// <summary>Tracks which methods were called and their arguments.</summary>
    public List<(string Method, Dictionary<string, object?> Args)> CallLog { get; } = new();

    // ── Factory methods ──

    /// <summary>
    /// Creates a MockInventorProvider where every method returns the given error message.
    /// </summary>
    public static MockInventorProvider WithError(string message)
    {
        var mock = new MockInventorProvider();
        var errorResult = new Dictionary<string, object?>
        {
            ["success"] = false,
            ["error"] = message,
        };

        mock._connectResult = errorResult;
        mock._disconnectResult = errorResult;
        mock._healthResult = errorResult;
        mock._docOpenResult = errorResult;
        mock._docNewPartResult = errorResult;
        mock._docNewAssemblyResult = errorResult;
        mock._docSaveResult = errorResult;
        mock._docSaveAsResult = errorResult;
        mock._docCloseResult = errorResult;
        mock._sketchCreateResult = errorResult;
        mock._sketchLineResult = errorResult;
        mock._sketchCircleResult = errorResult;
        mock._sketchArcResult = errorResult;
        mock._sketchRectangleResult = errorResult;
        mock._sketchDimensionResult = errorResult;
        mock._sketchPointResult = errorResult;
        mock._sketchSplineResult = errorResult;
        mock._sketchEllipseResult = errorResult;
        mock._sketchCircularPatternResult = errorResult;
        mock._sketchRectangularPatternResult = errorResult;
        mock._sketchOffsetResult = errorResult;
        mock._sketchMoveResult = errorResult;
        mock._sketchRotateResult = errorResult;
        mock._sketchDeleteResult = errorResult;
        mock._sketchConstraintResult = errorResult;
        mock._sketchTrimResult = errorResult;
        mock._sketchScaleResult = errorResult;
        mock._sketchMirrorResult = errorResult;
        mock._sketchLineCloseResult = errorResult;
        mock._sketchProfilesResult = errorResult;
        mock._extrudeResult = errorResult;
        mock._revolveResult = errorResult;
        mock._sweepResult = errorResult;
        mock._filletResult = errorResult;
        mock._chamferResult = errorResult;
        mock._circularPatternResult = errorResult;
        mock._mirrorFeatureResult = errorResult;
        mock._rectangularPatternResult = errorResult;
        mock._loftResult = errorResult;
        mock._coilResult = errorResult;
        mock._ribResult = errorResult;
        mock._embossResult = errorResult;
        mock._deriveResult = errorResult;
        mock._holeResult = errorResult;
        mock._threadResult = errorResult;
        mock._inspectEdgesResult = errorResult;
        mock._paramListResult = errorResult;
        mock._paramGetResult = errorResult;
        mock._paramSetResult = errorResult;
        mock._paramSetExpressionResult = errorResult;
        mock._iPropertyGetResult = errorResult;
        mock._iPropertySetResult = errorResult;
        mock._iPropertySummaryResult = errorResult;
        mock._iPropertyCustomGetResult = errorResult;
        mock._iPropertyCustomSetResult = errorResult;
        mock._exportStepResult = errorResult;
        mock._exportStlResult = errorResult;
        mock._exportPdfResult = errorResult;
        mock._exportDxfResult = errorResult;
        mock._workPlaneResult = errorResult;
        mock._workAxisResult = errorResult;
        mock._workPointResult = errorResult;
        mock._shellResult = errorResult;
        mock._draftResult = errorResult;
        mock._splitResult = errorResult;
        mock._combineResult = errorResult;
        mock._thickenResult = errorResult;

        return mock;
    }

    // ── Per-method setters for fine-grained control ──

    public MockInventorProvider SetConnectResult(Dictionary<string, object?> result)
    { _connectResult = result; return this; }
    public MockInventorProvider SetSketchCreateResult(Dictionary<string, object?> result)
    { _sketchCreateResult = result; return this; }
    public MockInventorProvider SetSketchLineResult(Dictionary<string, object?> result)
    { _sketchLineResult = result; return this; }
    public MockInventorProvider SetExtrudeResult(Dictionary<string, object?> result)
    { _extrudeResult = result; return this; }
    public MockInventorProvider SetRevolveResult(Dictionary<string, object?> result)
    { _revolveResult = result; return this; }
    public MockInventorProvider SetSweepResult(Dictionary<string, object?> result)
    { _sweepResult = result; return this; }
    public MockInventorProvider SetWorkPlaneResult(Dictionary<string, object?> result)
    { _workPlaneResult = result; return this; }
    public MockInventorProvider SetWorkAxisResult(Dictionary<string, object?> result)
    { _workAxisResult = result; return this; }
    public MockInventorProvider SetWorkPointResult(Dictionary<string, object?> result)
    { _workPointResult = result; return this; }
    public MockInventorProvider SetShellResult(Dictionary<string, object?> result)
    { _shellResult = result; return this; }
    public MockInventorProvider SetDraftResult(Dictionary<string, object?> result)
    { _draftResult = result; return this; }
    public MockInventorProvider SetSplitResult(Dictionary<string, object?> result)
    { _splitResult = result; return this; }
    public MockInventorProvider SetCombineResult(Dictionary<string, object?> result)
    { _combineResult = result; return this; }
    public MockInventorProvider SetThickenResult(Dictionary<string, object?> result)
    { _thickenResult = result; return this; }

    // ── ICadProvider implementation ──

    // Connection
    public Dictionary<string, object?> Connect()
    {
        CallLog.Add(("Connect", new Dictionary<string, object?>()));
        return _connectResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["version"] = "2025.1",
            ["connected"] = true,
        };
    }

    public Dictionary<string, object?> Disconnect()
    {
        CallLog.Add(("Disconnect", new Dictionary<string, object?>()));
        return _disconnectResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["disconnected"] = true,
        };
    }

    public Dictionary<string, object?> Health()
    {
        CallLog.Add(("Health", new Dictionary<string, object?>()));
        return _healthResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["version"] = "2025.1",
            ["active_document"] = "Part1.ipt",
            ["open_documents"] = 1,
        };
    }

    // Documents
    public Dictionary<string, object?> DocOpen(string path)
    {
        CallLog.Add(("DocOpen", new Dictionary<string, object?> { ["path"] = path }));
        return _docOpenResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["document"] = path,
        };
    }

    public Dictionary<string, object?> DocNewPart(string template = "")
    {
        CallLog.Add(("DocNewPart", new Dictionary<string, object?> { ["template"] = template }));
        return _docNewPartResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["document"] = "NewPart.ipt",
        };
    }

    public Dictionary<string, object?> DocNewAssembly(string template = "")
    {
        CallLog.Add(("DocNewAssembly", new Dictionary<string, object?> { ["template"] = template }));
        return _docNewAssemblyResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["document"] = "NewAssembly.iam",
        };
    }

    public Dictionary<string, object?> DocSave()
    {
        CallLog.Add(("DocSave", new Dictionary<string, object?>()));
        return _docSaveResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
        };
    }

    public Dictionary<string, object?> DocSaveAs(string path)
    {
        CallLog.Add(("DocSaveAs", new Dictionary<string, object?> { ["path"] = path }));
        return _docSaveAsResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["path"] = path,
        };
    }

    public Dictionary<string, object?> DocClose(bool save = true)
    {
        CallLog.Add(("DocClose", new Dictionary<string, object?> { ["save"] = save }));
        return _docCloseResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
        };
    }

    // Sketch
    public Dictionary<string, object?> SketchCreate(string plane = "XY")
    {
        CallLog.Add(("SketchCreate", new Dictionary<string, object?> { ["plane"] = plane }));
        return _sketchCreateResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["sketch"] = "Sketch1",
            ["plane"] = plane,
        };
    }

    public Dictionary<string, object?> SketchLine(double x1, double y1, double x2, double y2, string? tag = null, bool connect = false)
    {
        CallLog.Add(("SketchLine", new Dictionary<string, object?>
        {
            ["x1"] = x1, ["y1"] = y1, ["x2"] = x2, ["y2"] = y2,
            ["tag"] = tag, ["connect"] = connect,
        }));
        return _sketchLineResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["entity"] = 1,
            ["tag"] = tag,
        };
    }

    public Dictionary<string, object?> SketchCircle(double cx, double cy, double radius, string? tag = null)
    {
        CallLog.Add(("SketchCircle", new Dictionary<string, object?>
        {
            ["cx"] = cx, ["cy"] = cy, ["radius"] = radius, ["tag"] = tag,
        }));
        return _sketchCircleResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["entity"] = 1,
            ["tag"] = tag,
        };
    }

    public Dictionary<string, object?> SketchArc(double cx, double cy, double radius, double startAngle, double endAngle)
    {
        CallLog.Add(("SketchArc", new Dictionary<string, object?>
        {
            ["cx"] = cx, ["cy"] = cy, ["radius"] = radius,
            ["start_angle"] = startAngle, ["end_angle"] = endAngle,
        }));
        return _sketchArcResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["entity"] = 1,
        };
    }

    public Dictionary<string, object?> SketchRectangle(double x1, double y1, double x2, double y2)
    {
        CallLog.Add(("SketchRectangle", new Dictionary<string, object?>
        {
            ["x1"] = x1, ["y1"] = y1, ["x2"] = x2, ["y2"] = y2,
        }));
        return _sketchRectangleResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["entities"] = 4,
        };
    }

    public Dictionary<string, object?> SketchDimension(
        string mode, string entity1, string entity2 = "",
        double? value = null, string orientation = "aligned",
        double? positionX = null, double? positionY = null)
    {
        CallLog.Add(("SketchDimension", new Dictionary<string, object?>
        {
            ["mode"] = mode, ["entity1"] = entity1, ["entity2"] = entity2,
        }));
        return _sketchDimensionResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
        };
    }

    public Dictionary<string, object?> SketchPoint(double x, double y)
    {
        CallLog.Add(("SketchPoint", new Dictionary<string, object?> { ["x"] = x, ["y"] = y }));
        return _sketchPointResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["entity"] = 1,
        };
    }

    public Dictionary<string, object?> SketchSpline(string points, string fitMethod = "sweet")
    {
        CallLog.Add(("SketchSpline", new Dictionary<string, object?>
        {
            ["points"] = points, ["fit_method"] = fitMethod,
        }));
        return _sketchSplineResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["entity"] = 1,
        };
    }

    public Dictionary<string, object?> SketchEllipse(double cx, double cy, double majorRadius, double minorRadius, double majorAxisAngle = 0.0)
    {
        CallLog.Add(("SketchEllipse", new Dictionary<string, object?>
        {
            ["cx"] = cx, ["cy"] = cy,
            ["major_radius"] = majorRadius, ["minor_radius"] = minorRadius,
        }));
        return _sketchEllipseResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["entity"] = 1,
        };
    }

    public Dictionary<string, object?> SketchCircularPattern(
        string entities, string axis, int count,
        double angle = 360.0, bool fitted = true, bool symmetric = false)
    {
        CallLog.Add(("SketchCircularPattern", new Dictionary<string, object?>
        {
            ["entities"] = entities, ["axis"] = axis, ["count"] = count,
        }));
        return _sketchCircularPatternResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["instance_count"] = count,
        };
    }

    public Dictionary<string, object?> SketchRectangularPattern(
        string entities, string xAxis, int xCount, double xSpacing,
        string yAxis = "", int yCount = 1, double ySpacing = 0.0)
    {
        CallLog.Add(("SketchRectangularPattern", new Dictionary<string, object?>
        {
            ["entities"] = entities, ["x_axis"] = xAxis,
            ["x_count"] = xCount, ["x_spacing"] = xSpacing,
        }));
        return _sketchRectangularPatternResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
        };
    }

    public Dictionary<string, object?> SketchOffset(string entities, double offsetX, double offsetY, bool includeConnected = false)
    {
        CallLog.Add(("SketchOffset", new Dictionary<string, object?>
        {
            ["entities"] = entities, ["offset_x"] = offsetX, ["offset_y"] = offsetY,
        }));
        return _sketchOffsetResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
        };
    }

    public Dictionary<string, object?> SketchMove(string entities, double dx, double dy, bool copy = false)
    {
        CallLog.Add(("SketchMove", new Dictionary<string, object?>
        {
            ["entities"] = entities, ["dx"] = dx, ["dy"] = dy,
        }));
        return _sketchMoveResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
        };
    }

    public Dictionary<string, object?> SketchRotate(string entities, double cx, double cy, double angle, bool copy = false)
    {
        CallLog.Add(("SketchRotate", new Dictionary<string, object?>
        {
            ["entities"] = entities, ["cx"] = cx, ["cy"] = cy, ["angle"] = angle,
        }));
        return _sketchRotateResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
        };
    }

    public Dictionary<string, object?> SketchDelete()
    {
        CallLog.Add(("SketchDelete", new Dictionary<string, object?>()));
        return _sketchDeleteResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
        };
    }

    public Dictionary<string, object?> SketchConstraint(
        string mode, string entity1, string entity2 = "",
        string symLine = "", string axis = "major")
    {
        CallLog.Add(("SketchConstraint", new Dictionary<string, object?>
        {
            ["mode"] = mode, ["entity1"] = entity1, ["entity2"] = entity2,
        }));
        return _sketchConstraintResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
        };
    }

    public Dictionary<string, object?> SketchTrim(string entity, string cuttingEntity, string side = "end")
    {
        CallLog.Add(("SketchTrim", new Dictionary<string, object?>
        {
            ["entity"] = entity, ["cutting_entity"] = cuttingEntity, ["side"] = side,
        }));
        return _sketchTrimResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
        };
    }

    public Dictionary<string, object?> SketchScale(string entities, double cx, double cy, double factor)
    {
        CallLog.Add(("SketchScale", new Dictionary<string, object?>
        {
            ["entities"] = entities, ["cx"] = cx, ["cy"] = cy, ["factor"] = factor,
        }));
        return _sketchScaleResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
        };
    }

    public Dictionary<string, object?> SketchMirror(string entities, string mirrorEntity)
    {
        CallLog.Add(("SketchMirror", new Dictionary<string, object?>
        {
            ["entities"] = entities, ["mirror_entity"] = mirrorEntity,
        }));
        return _sketchMirrorResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
        };
    }

    // Skills
    public Dictionary<string, object?> SketchLineClose()
    {
        CallLog.Add(("SketchLineClose", new Dictionary<string, object?>()));
        return _sketchLineCloseResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
        };
    }

    public Dictionary<string, object?> SketchProfiles()
    {
        CallLog.Add(("SketchProfiles", new Dictionary<string, object?>()));
        return _sketchProfilesResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["profile_count"] = 1,
            ["profiles"] = new List<Dictionary<string, object?>>
            {
                new() { ["index"] = 1, ["area"] = 78.54, ["perimeter"] = 31.42, ["loops"] = 1 },
            },
        };
    }

    // Features
    public Dictionary<string, object?> Extrude(
        string profile, double distance, string direction = "positive",
        double taper = 0.0, string operation = "new_body")
    {
        CallLog.Add(("Extrude", new Dictionary<string, object?>
        {
            ["profile"] = profile, ["distance"] = distance,
            ["direction"] = direction, ["operation"] = operation,
        }));
        return _extrudeResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["feature"] = "Extrusion1",
        };
    }

    public Dictionary<string, object?> Revolve(
        string profile, string axis, double angle = 360.0,
        string direction = "positive", string operation = "join")
    {
        CallLog.Add(("Revolve", new Dictionary<string, object?>
        {
            ["profile"] = profile, ["axis"] = axis, ["angle"] = angle,
            ["direction"] = direction, ["operation"] = operation,
        }));
        return _revolveResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["feature"] = "Revolution1",
        };
    }

    public Dictionary<string, object?> Sweep(
        string profile, string path, string sweepType = "path",
        string operation = "new_body", double taper = 0,
        string pathSketch = "", string profileSketch = "")
    {
        CallLog.Add(("Sweep", new Dictionary<string, object?>
        {
            ["profile"] = profile, ["path"] = path, ["sweep_type"] = sweepType,
            ["operation"] = operation, ["taper"] = taper,
            ["path_sketch"] = pathSketch, ["profile_sketch"] = profileSketch,
        }));
        return _sweepResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["feature"] = "Sweep1",
        };
    }

    public Dictionary<string, object?> Fillet(string edges, double radius, string mode = "constant")
    {
        CallLog.Add(("Fillet", new Dictionary<string, object?>
        {
            ["edges"] = edges, ["radius"] = radius, ["mode"] = mode,
        }));
        return _filletResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["feature"] = "Fillet1",
        };
    }

    public Dictionary<string, object?> Chamfer(string edges, double distance, string mode = "equal_distance")
    {
        CallLog.Add(("Chamfer", new Dictionary<string, object?>
        {
            ["edges"] = edges, ["distance"] = distance, ["mode"] = mode,
        }));
        return _chamferResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["feature"] = "Chamfer1",
        };
    }

    public Dictionary<string, object?> CircularPattern(
        string profile, string axis, int count,
        double angle = 360.0, bool fitWithinAngle = true,
        bool naturalDirection = true)
    {
        CallLog.Add(("CircularPattern", new Dictionary<string, object?>
        {
            ["profile"] = profile, ["axis"] = axis, ["count"] = count,
        }));
        return _circularPatternResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["feature"] = "CircularPattern1",
        };
    }

    public Dictionary<string, object?> MirrorFeature(string profile, string mirrorPlane)
    {
        CallLog.Add(("MirrorFeature", new Dictionary<string, object?>
        {
            ["profile"] = profile, ["mirror_plane"] = mirrorPlane,
        }));
        return _mirrorFeatureResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["feature"] = "Mirror1",
        };
    }

    public Dictionary<string, object?> RectangularPattern(
        string profile, string xAxis, int xCount, double xSpacing,
        string yAxis = "", int yCount = 1, double ySpacing = 0.0)
    {
        CallLog.Add(("RectangularPattern", new Dictionary<string, object?>
        {
            ["profile"] = profile, ["x_axis"] = xAxis, ["x_count"] = xCount,
        }));
        return _rectangularPatternResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["feature"] = "RectPattern1",
        };
    }

    public Dictionary<string, object?> Loft(string profiles, string operation = "new_body")
    {
        CallLog.Add(("Loft", new Dictionary<string, object?> { ["profiles"] = profiles }));
        return _loftResult ?? new Dictionary<string, object?> { ["success"] = true, ["feature"] = "Loft1" };
    }

    public Dictionary<string, object?> Coil(string profile, string axis, double pitch, double revolutions, string operation = "new_body")
    {
        CallLog.Add(("Coil", new Dictionary<string, object?> { ["profile"] = profile }));
        return _coilResult ?? new Dictionary<string, object?> { ["success"] = true, ["feature"] = "Coil1" };
    }

    public Dictionary<string, object?> Rib(string profile, double thickness, string direction = "normal", string operation = "new_body")
    {
        CallLog.Add(("Rib", new Dictionary<string, object?> { ["profile"] = profile }));
        return _ribResult ?? new Dictionary<string, object?> { ["success"] = true, ["feature"] = "Rib1" };
    }

    public Dictionary<string, object?> Emboss(string profile, double depth, string type = "emboss_from_face")
    {
        CallLog.Add(("Emboss", new Dictionary<string, object?> { ["profile"] = profile }));
        return _embossResult ?? new Dictionary<string, object?> { ["success"] = true, ["feature"] = "Emboss1" };
    }

    public Dictionary<string, object?> Derive(string sourcePath)
    {
        CallLog.Add(("Derive", new Dictionary<string, object?> { ["source"] = sourcePath }));
        return _deriveResult ?? new Dictionary<string, object?> { ["success"] = true, ["feature"] = "Derive1" };
    }

    public Dictionary<string, object?> Hole(
        double x, double y, double diameter, double depth,
        string type = "drilled", string operation = "join")
    {
        CallLog.Add(("Hole", new Dictionary<string, object?>
        {
            ["x"] = x, ["y"] = y, ["diameter"] = diameter,
            ["depth"] = depth, ["type"] = type,
        }));
        return _holeResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["feature"] = "Hole1",
        };
    }

    public Dictionary<string, object?> Thread(string face, string specification, string direction = "right")
    {
        CallLog.Add(("Thread", new Dictionary<string, object?>
        {
            ["face"] = face, ["specification"] = specification,
        }));
        return _threadResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["feature"] = "Thread1",
        };
    }

    public Dictionary<string, object?> InspectEdges()
    {
        CallLog.Add(("InspectEdges", new Dictionary<string, object?>()));
        return _inspectEdgesResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["edges"] = new List<Dictionary<string, object?>>(),
        };
    }

    public Dictionary<string, object?> Shell(
        string faces, double thickness, string direction = "inside", string operation = "new_body")
    {
        CallLog.Add(("Shell", new Dictionary<string, object?>
        {
            ["faces"] = faces, ["thickness"] = thickness,
            ["direction"] = direction, ["operation"] = operation,
        }));
        return _shellResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["feature_type"] = "shell",
            ["thickness"] = thickness,
            ["feature_name"] = "MockShell1",
        };
    }

    public Dictionary<string, object?> Draft(
        string faces, double angle, string mode = "fixed_edge",
        string pullDirection = "z", string fixedEntity = "")
    {
        CallLog.Add(("Draft", new Dictionary<string, object?>
        {
            ["faces"] = faces, ["angle"] = angle,
            ["mode"] = mode, ["pull_direction"] = pullDirection,
            ["fixed_entity"] = fixedEntity,
        }));
        return _draftResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["feature_type"] = "draft",
            ["angle"] = angle,
            ["feature_name"] = "MockDraft1",
        };
    }

    public Dictionary<string, object?> Split(
        string splitTool, string removeSide = "positive", string targetBody = "")
    {
        CallLog.Add(("Split", new Dictionary<string, object?>
        {
            ["split_tool"] = splitTool, ["remove_side"] = removeSide,
            ["target_body"] = targetBody,
        }));
        return _splitResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["feature_type"] = "split",
            ["feature_name"] = "MockSplit1",
        };
    }

    public Dictionary<string, object?> Combine(
        string baseBody, string toolBodies, string operation = "join", bool keepToolBodies = false)
    {
        CallLog.Add(("Combine", new Dictionary<string, object?>
        {
            ["base_body"] = baseBody, ["tool_bodies"] = toolBodies,
            ["operation"] = operation, ["keep_tool_bodies"] = keepToolBodies,
        }));
        return _combineResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["feature_type"] = "combine",
            ["operation"] = operation,
            ["feature_name"] = "MockCombine1",
        };
    }

    public Dictionary<string, object?> Thicken(
        string faces, double thickness, string direction = "positive", string operation = "new_body")
    {
        CallLog.Add(("Thicken", new Dictionary<string, object?>
        {
            ["faces"] = faces, ["thickness"] = thickness,
            ["direction"] = direction, ["operation"] = operation,
        }));
        return _thickenResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["feature_type"] = "thicken",
            ["thickness"] = thickness,
            ["feature_name"] = "MockThicken1",
        };
    }

    // Parameters
    public Dictionary<string, object?> ParamList(string? filterPattern = null)
    {
        CallLog.Add(("ParamList", new Dictionary<string, object?> { ["filter_pattern"] = filterPattern }));
        return _paramListResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["parameters"] = new List<Dictionary<string, object?>>(),
        };
    }

    public Dictionary<string, object?> ParamGet(string name)
    {
        CallLog.Add(("ParamGet", new Dictionary<string, object?> { ["name"] = name }));
        return _paramGetResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["name"] = name,
            ["value"] = 10.0,
        };
    }

    public Dictionary<string, object?> ParamSet(string name, double value)
    {
        CallLog.Add(("ParamSet", new Dictionary<string, object?> { ["name"] = name, ["value"] = value }));
        return _paramSetResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["name"] = name,
            ["value"] = value,
        };
    }

    public Dictionary<string, object?> ParamSetExpression(string name, string expression)
    {
        CallLog.Add(("ParamSetExpression", new Dictionary<string, object?> { ["name"] = name, ["expression"] = expression }));
        return _paramSetExpressionResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["name"] = name,
            ["expression"] = expression,
        };
    }

    // Properties
    public Dictionary<string, object?> IPropertyGet(string name, string propertySet = "Summary")
    {
        CallLog.Add(("IPropertyGet", new Dictionary<string, object?> { ["name"] = name, ["property_set"] = propertySet }));
        return _iPropertyGetResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["name"] = name,
            ["value"] = "TestValue",
        };
    }

    public Dictionary<string, object?> IPropertySet(string name, string? value, string propertySet = "Summary")
    {
        CallLog.Add(("IPropertySet", new Dictionary<string, object?> { ["name"] = name, ["value"] = value }));
        return _iPropertySetResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
        };
    }

    public Dictionary<string, object?> IPropertySummary()
    {
        CallLog.Add(("IPropertySummary", new Dictionary<string, object?>()));
        return _iPropertySummaryResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["title"] = "Test Title",
            ["author"] = "Test Author",
        };
    }

    public Dictionary<string, object?> IPropertyCustomGet(string name)
    {
        CallLog.Add(("IPropertyCustomGet", new Dictionary<string, object?> { ["name"] = name }));
        return _iPropertyCustomGetResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["name"] = name,
            ["value"] = "CustomValue",
        };
    }

    public Dictionary<string, object?> IPropertyCustomSet(string name, string? value)
    {
        CallLog.Add(("IPropertyCustomSet", new Dictionary<string, object?> { ["name"] = name, ["value"] = value }));
        return _iPropertyCustomSetResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
        };
    }

    // Export
    public Dictionary<string, object?> ExportStep(string path, Dictionary<string, object?>? options = null)
    {
        CallLog.Add(("ExportStep", new Dictionary<string, object?> { ["path"] = path }));
        return _exportStepResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["path"] = path,
        };
    }

    public Dictionary<string, object?> ExportStl(string path, Dictionary<string, object?>? options = null)
    {
        CallLog.Add(("ExportStl", new Dictionary<string, object?> { ["path"] = path }));
        return _exportStlResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["path"] = path,
        };
    }

    public Dictionary<string, object?> ExportPdf(string path, Dictionary<string, object?>? options = null)
    {
        CallLog.Add(("ExportPdf", new Dictionary<string, object?> { ["path"] = path }));
        return _exportPdfResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["path"] = path,
        };
    }

    public Dictionary<string, object?> ExportDxf(string path, Dictionary<string, object?>? options = null)
    {
        CallLog.Add(("ExportDxf", new Dictionary<string, object?> { ["path"] = path }));
        return _exportDxfResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["path"] = path,
        };
    }

    // Work Features
    public Dictionary<string, object?> WorkPlane(string definition, string reference1, string reference2, double offset)
    {
        CallLog.Add(("WorkPlane", new Dictionary<string, object?>
        {
            ["definition"] = definition,
            ["reference1"] = reference1,
            ["reference2"] = reference2,
            ["offset"] = offset,
        }));
        return _workPlaneResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["plane"] = new Dictionary<string, object?>
            {
                ["name"] = "WorkPlane1",
                ["id"] = "WorkPlane1",
            },
        };
    }

    public Dictionary<string, object?> WorkAxis(string definition, string reference1, string reference2)
    {
        CallLog.Add(("WorkAxis", new Dictionary<string, object?>
        {
            ["definition"] = definition,
            ["reference1"] = reference1,
            ["reference2"] = reference2,
        }));
        return _workAxisResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["axis"] = new Dictionary<string, object?>
            {
                ["name"] = "WorkAxis1",
                ["id"] = "WorkAxis1",
            },
        };
    }

    public Dictionary<string, object?> WorkPoint(string definition, string reference1, string reference2, string reference3)
    {
        CallLog.Add(("WorkPoint", new Dictionary<string, object?>
        {
            ["definition"] = definition,
            ["reference1"] = reference1,
            ["reference2"] = reference2,
            ["reference3"] = reference3,
        }));
        return _workPointResult ?? new Dictionary<string, object?>
        {
            ["success"] = true,
            ["point"] = new Dictionary<string, object?>
            {
                ["name"] = "WorkPoint1",
                ["id"] = "WorkPoint1",
            },
        };
    }

    // Assembly
    public Dictionary<string, object?> AsmListComponents()
    {
        CallLog.Add(("AsmListComponents", new Dictionary<string, object?>()));
        return new Dictionary<string, object?> { ["success"] = true, ["occurrences"] = new List<Dictionary<string, object?>>() };
    }
    public Dictionary<string, object?> AsmListConstraints()
    {
        CallLog.Add(("AsmListConstraints", new Dictionary<string, object?>()));
        return new Dictionary<string, object?> { ["success"] = true, ["constraints"] = new List<Dictionary<string, object?>>() };
    }
    public Dictionary<string, object?> AsmPlaceComponent(string path, double x = 0, double y = 0, double z = 0)
    {
        CallLog.Add(("AsmPlaceComponent", new Dictionary<string, object?> { ["path"] = path, ["x"] = x, ["y"] = y, ["z"] = z }));
        return new Dictionary<string, object?> { ["success"] = true, ["component_name"] = "Component1" };
    }
    public Dictionary<string, object?> AsmGroundComponent(string occurrence)
    {
        CallLog.Add(("AsmGroundComponent", new Dictionary<string, object?> { ["occurrence"] = occurrence }));
        return new Dictionary<string, object?> { ["success"] = true, ["grounded"] = true };
    }
    public Dictionary<string, object?> AsmReplaceComponent(string occurrence, string newPath)
    {
        CallLog.Add(("AsmReplaceComponent", new Dictionary<string, object?> { ["occurrence"] = occurrence, ["new_path"] = newPath }));
        return new Dictionary<string, object?> { ["success"] = true };
    }
    public Dictionary<string, object?> AsmDeleteConstraint(string constraint)
    {
        CallLog.Add(("AsmDeleteConstraint", new Dictionary<string, object?> { ["constraint"] = constraint }));
        return new Dictionary<string, object?> { ["success"] = true };
    }
    public Dictionary<string, object?> AsmConstraintMate(string entityOne, string entityTwo, double offset = 0)
    {
        CallLog.Add(("AsmConstraintMate", new Dictionary<string, object?> { ["entity_one"] = entityOne, ["entity_two"] = entityTwo, ["offset"] = offset }));
        return new Dictionary<string, object?> { ["success"] = true, ["constraint_type"] = "mate", ["constraint_name"] = "Mate1" };
    }
    public Dictionary<string, object?> AsmConstraintFlush(string entityOne, string entityTwo, double offset = 0)
    {
        CallLog.Add(("AsmConstraintFlush", new Dictionary<string, object?> { ["entity_one"] = entityOne, ["entity_two"] = entityTwo, ["offset"] = offset }));
        return new Dictionary<string, object?> { ["success"] = true, ["constraint_type"] = "flush", ["constraint_name"] = "Flush1" };
    }
    public Dictionary<string, object?> AsmConstraintAngle(string entityOne, string entityTwo, double angle, string solution = "directed")
    {
        CallLog.Add(("AsmConstraintAngle", new Dictionary<string, object?> { ["entity_one"] = entityOne, ["entity_two"] = entityTwo, ["angle"] = angle }));
        return new Dictionary<string, object?> { ["success"] = true, ["constraint_type"] = "angle", ["constraint_name"] = "Angle1" };
    }
    public Dictionary<string, object?> AsmConstraintInsert(string entityOne, string entityTwo, double offset = 0)
    {
        CallLog.Add(("AsmConstraintInsert", new Dictionary<string, object?> { ["entity_one"] = entityOne, ["entity_two"] = entityTwo, ["offset"] = offset }));
        return new Dictionary<string, object?> { ["success"] = true, ["constraint_type"] = "insert", ["constraint_name"] = "Insert1" };
    }
    public Dictionary<string, object?> AsmConstraintTangent(string entityOne, string entityTwo, double offset = 0)
    {
        CallLog.Add(("AsmConstraintTangent", new Dictionary<string, object?> { ["entity_one"] = entityOne, ["entity_two"] = entityTwo, ["offset"] = offset }));
        return new Dictionary<string, object?> { ["success"] = true, ["constraint_type"] = "tangent", ["constraint_name"] = "Tangent1" };
    }
    public Dictionary<string, object?> AsmCircularPattern(string occurrence, string axis, int count, double angle = 360)
    {
        CallLog.Add(("AsmCircularPattern", new Dictionary<string, object?> { ["occurrence"] = occurrence, ["axis"] = axis, ["count"] = count }));
        return new Dictionary<string, object?> { ["success"] = true, ["pattern_type"] = "circular" };
    }
    public Dictionary<string, object?> AsmRectangularPattern(string occurrence, string xAxis, int xCount, double xSpacing, string? yAxis = null, int yCount = 1, double ySpacing = 0)
    {
        CallLog.Add(("AsmRectangularPattern", new Dictionary<string, object?> { ["occurrence"] = occurrence, ["x_axis"] = xAxis, ["x_count"] = xCount }));
        return new Dictionary<string, object?> { ["success"] = true, ["pattern_type"] = "rectangular" };
    }
    public Dictionary<string, object?> AsmExtrudeCut(string profile, double distance, string direction = "positive")
    {
        CallLog.Add(("AsmExtrudeCut", new Dictionary<string, object?> { ["profile"] = profile, ["distance"] = distance }));
        return new Dictionary<string, object?> { ["success"] = true, ["feature_type"] = "assembly_extrude_cut" };
    }
    public Dictionary<string, object?> AsmHole(double x, double y, double diameter, double depth, string type = "drilled")
    {
        CallLog.Add(("AsmHole", new Dictionary<string, object?> { ["x"] = x, ["y"] = y, ["diameter"] = diameter, ["depth"] = depth }));
        return new Dictionary<string, object?> { ["success"] = true, ["feature_type"] = "assembly_hole" };
    }
    public Dictionary<string, object?> AsmBom()
    {
        CallLog.Add(("AsmBom", new Dictionary<string, object?>()));
        return new Dictionary<string, object?> { ["success"] = true, ["items"] = new List<Dictionary<string, object?>>() };
    }
}