namespace McpCad.Core;

/// <summary>
/// Provider interface for mechanical CAD operations (sketch, 3D features,
/// parameters, properties). Extends the common <see cref="ICadProvider"/>.
/// Implement for Inventor, SolidWorks, FreeCAD, etc.
/// </summary>
public interface IMechanicalCadProvider : ICadProvider
{
    #region Sketch

    Dictionary<string, object?> SketchCreate(string plane = "XY");
    Dictionary<string, object?> SketchLine(double x1, double y1, double x2, double y2, string? tag = null, bool connect = false);
    Dictionary<string, object?> SketchCircle(double cx, double cy, double radius, string? tag = null);
    Dictionary<string, object?> SketchArc(double cx, double cy, double radius, double startAngle, double endAngle);
    Dictionary<string, object?> SketchRectangle(double x1, double y1, double x2, double y2);
    Dictionary<string, object?> SketchDimension(string mode, string entity1, string entity2 = "", double? value = null, string orientation = "aligned", double? positionX = null, double? positionY = null);
    Dictionary<string, object?> SketchPoint(double x, double y);
    Dictionary<string, object?> SketchSpline(string points, string fitMethod = "sweet");
    Dictionary<string, object?> SketchEllipse(double cx, double cy, double majorRadius, double minorRadius, double majorAxisAngle = 0.0);
    Dictionary<string, object?> SketchCircularPattern(string entities, string axis, int count, double angle = 360.0, bool fitted = true, bool symmetric = false);
    Dictionary<string, object?> SketchRectangularPattern(string entities, string xAxis, int xCount, double xSpacing, string yAxis = "", int yCount = 1, double ySpacing = 0.0);
    Dictionary<string, object?> SketchOffset(string entities, double offsetX, double offsetY, bool includeConnected = false);
    Dictionary<string, object?> SketchMove(string entities, double dx, double dy, bool copy = false);
    Dictionary<string, object?> SketchRotate(string entities, double cx, double cy, double angle, bool copy = false);
    Dictionary<string, object?> SketchDelete();
    Dictionary<string, object?> SketchConstraint(string mode, string entity1, string entity2 = "", string symLine = "", string axis = "major");
    Dictionary<string, object?> SketchTrim(string entity, string cuttingEntity, string side = "end");
    Dictionary<string, object?> SketchScale(string entities, double cx, double cy, double factor);
    Dictionary<string, object?> SketchMirror(string entities, string mirrorEntity);
    Dictionary<string, object?> SketchLineClose();
    Dictionary<string, object?> SketchProfiles();

    #endregion

    #region Features

    Dictionary<string, object?> Extrude(string profile, double distance, string direction = "positive", double taper = 0.0, string operation = "new_body");
    Dictionary<string, object?> Revolve(string profile, string axis, double angle = 360.0, string direction = "positive", string operation = "join");
    Dictionary<string, object?> Sweep(string profile, string path, string sweepType = "path", string operation = "new_body", double taper = 0, string pathSketch = "", string profileSketch = "");
    Dictionary<string, object?> Fillet(string edges, double radius, string mode = "constant");
    Dictionary<string, object?> Chamfer(string edges, double distance, string mode = "equal_distance");
    Dictionary<string, object?> CircularPattern(string profile, string axis, int count, double angle = 360.0, bool fitWithinAngle = true, bool naturalDirection = true);
    Dictionary<string, object?> MirrorFeature(string profile, string mirrorPlane);
    Dictionary<string, object?> RectangularPattern(string profile, string xAxis, int xCount, double xSpacing, string yAxis = "", int yCount = 1, double ySpacing = 0.0);
    Dictionary<string, object?> Loft(string profiles, string operation = "new_body");
    Dictionary<string, object?> Coil(string profile, string axis, double pitch, double revolutions, string operation = "new_body");
    Dictionary<string, object?> Rib(string profile, double thickness, string direction = "normal", string operation = "new_body");
    Dictionary<string, object?> Emboss(string profile, double depth, string type = "emboss_from_face");
    Dictionary<string, object?> Derive(string sourcePath);
    Dictionary<string, object?> Hole(double x, double y, double diameter, double depth, string type = "drilled", string operation = "join");
    Dictionary<string, object?> Thread(string face, string specification, string direction = "right");
    Dictionary<string, object?> InspectEdges();
    Dictionary<string, object?> Shell(string faces, double thickness, string direction = "inside", string operation = "new_body");
    Dictionary<string, object?> Draft(string faces, double angle, string mode = "fixed_edge", string pullDirection = "z", string fixedEntity = "");
    Dictionary<string, object?> Split(string splitTool, string removeSide = "positive", string targetBody = "");
    Dictionary<string, object?> Combine(string baseBody, string toolBodies, string operation = "join", bool keepToolBodies = false);
    Dictionary<string, object?> Thicken(string faces, double thickness, string direction = "positive", string operation = "new_body");

    #endregion

    #region Parameters

    Dictionary<string, object?> ParamList(string? filterPattern = null);
    Dictionary<string, object?> ParamGet(string name);
    Dictionary<string, object?> ParamSet(string name, double value);
    Dictionary<string, object?> ParamSetExpression(string name, string expression);

    #endregion

    #region Properties

    Dictionary<string, object?> IPropertyGet(string name, string propertySet = "Summary");
    Dictionary<string, object?> IPropertySet(string name, string? value, string propertySet = "Summary");
    Dictionary<string, object?> IPropertySummary();
    Dictionary<string, object?> IPropertyCustomGet(string name);
    Dictionary<string, object?> IPropertyCustomSet(string name, string? value);

    #endregion

    #region WorkFeatures

    Dictionary<string, object?> WorkPlane(string definition, string reference1, string reference2, double offset);
    Dictionary<string, object?> WorkAxis(string definition, string reference1, string reference2);
    Dictionary<string, object?> WorkPoint(string definition, string reference1, string reference2, string reference3);

    #endregion

    #region Assembly

    Dictionary<string, object?> AsmListComponents();
    Dictionary<string, object?> AsmListConstraints();
    Dictionary<string, object?> AsmPlaceComponent(string path, double x = 0, double y = 0, double z = 0);
    Dictionary<string, object?> AsmGroundComponent(string occurrence);
    Dictionary<string, object?> AsmReplaceComponent(string occurrence, string newPath);
    Dictionary<string, object?> AsmDeleteConstraint(string constraint);
    Dictionary<string, object?> AsmConstraintMate(string entityOne, string entityTwo, double offset = 0);
    Dictionary<string, object?> AsmConstraintFlush(string entityOne, string entityTwo, double offset = 0);
    Dictionary<string, object?> AsmConstraintAngle(string entityOne, string entityTwo, double angle, string solution = "directed");
    Dictionary<string, object?> AsmConstraintInsert(string entityOne, string entityTwo, double offset = 0);
    Dictionary<string, object?> AsmConstraintTangent(string entityOne, string entityTwo, double offset = 0);
    Dictionary<string, object?> AsmCircularPattern(string occurrence, string axis, int count, double angle = 360);
    Dictionary<string, object?> AsmRectangularPattern(string occurrence, string xAxis, int xCount, double xSpacing, string? yAxis = null, int yCount = 1, double ySpacing = 0);
    Dictionary<string, object?> AsmExtrudeCut(string profile, double distance, string direction = "positive");
    Dictionary<string, object?> AsmHole(double x, double y, double diameter, double depth, string type = "drilled");
    Dictionary<string, object?> AsmBom();

    #endregion

    #region Inspection & Visual Feedback (for LLM self-verification / retroalimentación)

    /// <summary>
    /// Captures a screenshot of the active 3D viewport or CAD window.
    /// Returns Base64 encoded image for multimodal (vision) feedback to the LLM.
    /// Use after operations so the vision model can visually verify geometry, collisions, etc.
    /// </summary>
    Dictionary<string, object?> CaptureViewportImage(string view = "Iso", int width = 1024, int height = 768, string format = "png")
        => new() { ["success"] = false, ["error"] = "Viewport capture is not implemented by this provider." };

    /// <summary>
    /// Returns the full feature/operation tree of the active document.
    /// Allows the LLM to inspect the model structure (features, their order, dependencies)
    /// directly via data (no vision needed). Supports "Árbol de Operaciones" verification.
    /// </summary>
    Dictionary<string, object?> GetFeatureTree()
        => new() { ["success"] = false, ["error"] = "Feature tree inspection is not implemented by this provider." };

    /// <summary>
    /// Returns bounding box information for the whole model, a body, or a tagged entity.
    /// Useful for geometric verification (intersections, sizes) using direct vector data from Inventor API.
    /// </summary>
    Dictionary<string, object?> GetBoundingBox(string target = "")
        => new() { ["success"] = false, ["error"] = "Bounding box inspection is not implemented by this provider." };
    Dictionary<string, object?> GetBodyCount()
        => new() { ["success"] = false, ["error"] = "Body inspection is not implemented by this provider." };
    Dictionary<string, object?> InspectFeature(string target)
        => new() { ["success"] = false, ["error"] = "Feature inspection is not implemented by this provider." };
    Dictionary<string, object?> MeasureSection(string axis, double positionCm)
        => new() { ["success"] = false, ["error"] = "Section measurement is not implemented by this provider." };
    Dictionary<string, object?> CreateRevolvedProfile(string name, string mainAxis, string profilePointsJson)
        => new() { ["success"] = false, ["error"] = "Deterministic revolve is not implemented by this provider." };
    Dictionary<string, object?> CutKeyway(string name, string mainAxis, string targetSegment, double segmentStartCm, double segmentEndCm, double segmentDiameterCm, double axisStartCm, double axisEndCm, string radialDirection, double lengthCm, double widthCm, double depthCm)
        => new() { ["success"] = false, ["error"] = "Deterministic keyway is not implemented by this provider." };

    /// <summary>
    /// Structured JSON summary of the active part geometry (faces, edges, adjacency).
    /// Mirrors SimpleCADAPI inspect_step_rsummary. entity_id format: "face:N"/"edge:N" (zero-based).
    /// </summary>
    Dictionary<string, object?> GetModelJson(bool include_faces = true, bool include_edges = false, int max_faces = 64)
        => new() { ["success"] = false, ["error"] = "GetModelJson is not implemented by this provider." };

    /// <summary>
    /// Full geometry detail for one face or edge by entity_id ("face:N" or "edge:N", zero-based).
    /// Mirrors SimpleCADAPI inspect_step_entity_rdescriptor.
    /// </summary>
    Dictionary<string, object?> GetEntityDetail(string entity_id, int body_index = 0)
        => new() { ["success"] = false, ["error"] = "GetEntityDetail is not implemented by this provider." };

    #endregion
}
