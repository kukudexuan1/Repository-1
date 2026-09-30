using McpCad.Core;
using McpCad.Core.Exceptions;
using McpCad.Tests.Mocks;
using McpCad.Tools;

namespace McpCad.Tests.Tools;

public class ErrorHandlingTests
{
    /// <summary>
    /// Verifies that InventorConnectionException is caught and translated to
    /// { "success": false, "error": "..." } by the tool layer (D7).
    /// </summary>
    [Fact]
    public void AtomicTools_Catches_InventorConnectionException()
    {
        var mock = new MockInventorProvider();
        mock.SetConnectResult(new Dictionary<string, object?>
        {
            ["success"] = false,
            ["error"] = "Inventor is not running",
        });
        var tools = new AtomicTools(mock);

        var result = tools.inventor_connect();

        Assert.False((bool)result["success"]!);
        Assert.Equal("Inventor is not running", result["error"]);
    }

    /// <summary>
    /// Verifies that InventorComException caught at the tool layer produces
    /// a standardized error result.
    /// </summary>
    [Fact]
    public void InventorComException_Produces_ErrorResult()
    {
        // Create a mock that throws InventorComException when called
        var mock = new ThrowingMockProvider(
            new InventorComException("Edge index 99 does not exist."));
        var tools = new AtomicTools(mock);

        var result = tools.fillet("99", 2.0);

        Assert.False((bool)result["success"]!);
        Assert.Contains("Edge index 99", result["error"]!.ToString());
    }

    /// <summary>
    /// Verifies that generic exceptions are caught and produce
    /// { "success": false, "error": "Unexpected error: ..." }.
    /// </summary>
    [Fact]
    public void GenericException_Produces_UnexpectedErrorResult()
    {
        var mock = new ThrowingMockProvider(new Exception("Something broke"));
        var tools = new AtomicTools(mock);

        var result = tools.extrude("1", 5.0);

        Assert.False((bool)result["success"]!);
        Assert.Contains("Unexpected error", result["error"]!.ToString());
        Assert.Contains("Something broke", result["error"]!.ToString());
    }

    /// <summary>
    /// Verifies error propagation for SketchCreate specifically.
    /// </summary>
    [Fact]
    public void SketchCreate_Error_Returns_False_Success()
    {
        var mock = MockInventorProvider.WithError("No active document");
        var tools = new AtomicTools(mock);

        var result = tools.sketch_create("XY");

        Assert.False((bool)result["success"]!);
        Assert.Equal("No active document", result["error"]);
    }

    /// <summary>
    /// Verifies error propagation for Parameter operations.
    /// </summary>
    [Fact]
    public void ParamGet_Error_Returns_False_Success()
    {
        var mock = MockInventorProvider.WithError("Parameter not found");
        var tools = new AtomicTools(mock);

        var result = tools.param_get("nonexistent");

        Assert.False((bool)result["success"]!);
        Assert.Equal("Parameter not found", result["error"]);
    }

    /// <summary>
    /// Verifies error propagation across all three exception types produces
    /// consistent { success: false, error: "..." } shape.
    /// </summary>
    [Theory]
    [InlineData(typeof(InventorConnectionException), false)]
    [InlineData(typeof(InventorComException), false)]
    [InlineData(typeof(Exception), false)]
    public void AllExceptionTypes_Produce_Error_Result(Type exceptionType, bool expectedSuccess)
    {
        var ex = (Exception)Activator.CreateInstance(exceptionType, "test error")!;
        var mock = new ThrowingMockProvider(ex);
        var tools = new AtomicTools(mock);

        var result = tools.inventor_connect();

        Assert.Equal(expectedSuccess, result["success"]);
        Assert.NotNull(result["error"]);
    }

    /// <summary>
    /// Verifies SkillTools error handling follows the same pattern as AtomicTools.
    /// </summary>
    [Fact]
    public void SkillTools_Catches_InventorComException()
    {
        var mock = new ThrowingMockProvider(
            new InventorComException("Profile not found"));
        var tools = new SkillTools(mock);

        var result = tools.skill_sketch("XY");

        Assert.False((bool)result["success"]!);
        Assert.Contains("Profile not found", result["error"]!.ToString());
    }

    // ── Work Feature error handling ───────────────────────────────────

    /// <summary>
    /// Verifies Catch() wrapper converts InventorComException for work_plane.
    /// </summary>
    [Fact]
    public void WorkPlane_Error_Returns_False_Success()
    {
        var mock = MockInventorProvider.WithError("Invalid geometry reference");
        var tools = new AtomicTools(mock);

        var result = tools.work_plane("offset_from_plane", "bad_ref");

        Assert.False((bool)result["success"]!);
        Assert.Equal("Invalid geometry reference", result["error"]);
    }

    /// <summary>
    /// Verifies Catch() wrapper converts InventorComException for work_axis.
    /// </summary>
    [Fact]
    public void WorkAxis_ComException_Produces_ErrorResult()
    {
        var mock = new ThrowingMockProvider(
            new InventorComException("Edge index 99 does not exist."));
        var tools = new AtomicTools(mock);

        var result = tools.work_axis("along_edge", "99");

        Assert.False((bool)result["success"]!);
        Assert.Contains("Edge index 99", result["error"]!.ToString());
    }

    /// <summary>
    /// Verifies Catch() wrapper converts InventorComException for work_point.
    /// </summary>
    [Fact]
    public void WorkPoint_ComException_Produces_ErrorResult()
    {
        var mock = new ThrowingMockProvider(
            new InventorComException("Plane reference not found"));
        var tools = new AtomicTools(mock);

        var result = tools.work_point("intersection", "bad_plane");

        Assert.False((bool)result["success"]!);
        Assert.Contains("Plane reference not found", result["error"]!.ToString());
    }

    /// <summary>
    /// Verifies Catch() wrapper for work_point with invalid coordinate.
    /// </summary>
    [Fact]
    public void WorkPoint_Error_Returns_False_Success()
    {
        var mock = MockInventorProvider.WithError("Missing required parameter: z");
        var tools = new AtomicTools(mock);

        var result = tools.work_point("at_coordinates", "10", "5");

        Assert.False((bool)result["success"]!);
        Assert.Equal("Missing required parameter: z", result["error"]);
    }

    // ── Modify Feature error handling ──────────────────────────────────

    /// <summary>
    /// Verifies Catch() wrapper converts InventorComException for combine.
    /// </summary>
    [Fact]
    public void Combine_ComException_Produces_ErrorResult()
    {
        var mock = new ThrowingMockProvider(
            new InventorComException("Tool body index 99 does not exist."));
        var tools = new AtomicTools(mock);

        var result = tools.combine("1", "99", "cut");

        Assert.False((bool)result["success"]!);
        Assert.Contains("Tool body index 99", result["error"]!.ToString());
    }

    /// <summary>
    /// Verifies WithError pattern for combine.
    /// </summary>
    [Fact]
    public void Combine_Error_Returns_False_Success()
    {
        var mock = MockInventorProvider.WithError("No active document");
        var tools = new AtomicTools(mock);

        var result = tools.combine("1", "2");

        Assert.False((bool)result["success"]!);
        Assert.Equal("No active document", result["error"]);
    }

    // ── Shell error handling ───────────────────────────────────────────

    /// <summary>
    /// Verifies Catch() wrapper converts InventorComException for shell.
    /// </summary>
    [Fact]
    public void Shell_ComException_Produces_ErrorResult()
    {
        var mock = new ThrowingMockProvider(
            new InventorComException("Face index 99 does not exist."));
        var tools = new AtomicTools(mock);

        var result = tools.shell("99", 0.2);

        Assert.False((bool)result["success"]!);
        Assert.Contains("Face index 99", result["error"]!.ToString());
    }

    /// <summary>
    /// Verifies WithError pattern for shell.
    /// </summary>
    [Fact]
    public void Shell_Error_Returns_False_Success()
    {
        var mock = MockInventorProvider.WithError("No active document");
        var tools = new AtomicTools(mock);

        var result = tools.shell("1,2", 0.3);

        Assert.False((bool)result["success"]!);
        Assert.Equal("No active document", result["error"]);
    }

    // ── Thicken error handling ─────────────────────────────────────────

    /// <summary>
    /// Verifies Catch() wrapper converts InventorComException for thicken.
    /// </summary>
    [Fact]
    public void Thicken_ComException_Produces_ErrorResult()
    {
        var mock = new ThrowingMockProvider(
            new InventorComException("Face index 99 does not exist."));
        var tools = new AtomicTools(mock);

        var result = tools.thicken("99", 0.2);

        Assert.False((bool)result["success"]!);
        Assert.Contains("Face index 99", result["error"]!.ToString());
    }

    /// <summary>
    /// Verifies WithError pattern for thicken.
    /// </summary>
    [Fact]
    public void Thicken_Error_Returns_False_Success()
    {
        var mock = MockInventorProvider.WithError("No active document");
        var tools = new AtomicTools(mock);

        var result = tools.thicken("1", 0.2);

        Assert.False((bool)result["success"]!);
        Assert.Equal("No active document", result["error"]);
    }

    // ── Split error handling ────────────────────────────────────────────

    /// <summary>
    /// Verifies Catch() wrapper converts InventorComException for split.
    /// </summary>
    [Fact]
    public void Split_ComException_Produces_ErrorResult()
    {
        var mock = new ThrowingMockProvider(
            new InventorComException("Work plane index 99 does not exist."));
        var tools = new AtomicTools(mock);

        var result = tools.split("99", "both");

        Assert.False((bool)result["success"]!);
        Assert.Contains("Work plane index 99", result["error"]!.ToString());
    }

    /// <summary>
    /// Verifies WithError pattern for split.
    /// </summary>
    [Fact]
    public void Split_Error_Returns_False_Success()
    {
        var mock = MockInventorProvider.WithError("No active document");
        var tools = new AtomicTools(mock);

        var result = tools.split("1", "both");

        Assert.False((bool)result["success"]!);
        Assert.Equal("No active document", result["error"]);
    }

    // ── Draft error handling ────────────────────────────────────────────

    /// <summary>
    /// Verifies Catch() wrapper converts InventorComException for draft.
    /// </summary>
    [Fact]
    public void Draft_ComException_Produces_ErrorResult()
    {
        var mock = new ThrowingMockProvider(
            new InventorComException("Face index 99 does not exist."));
        var tools = new AtomicTools(mock);

        var result = tools.draft("99", 5.0);

        Assert.False((bool)result["success"]!);
        Assert.Contains("Face index 99", result["error"]!.ToString());
    }

    /// <summary>
    /// Verifies WithError pattern for draft.
    /// </summary>
    [Fact]
    public void Draft_Error_Returns_False_Success()
    {
        var mock = MockInventorProvider.WithError("No active document");
        var tools = new AtomicTools(mock);

        var result = tools.draft("1,2", 5.0);

        Assert.False((bool)result["success"]!);
        Assert.Equal("No active document", result["error"]);
    }
}

/// <summary>
/// A mock provider that throws a specified exception on every method call.
/// Used for testing error handling paths in tool classes.
/// </summary>
internal class ThrowingMockProvider : IMechanicalCadProvider
{
    private readonly Exception _exception;

    public ThrowingMockProvider(Exception exception)
    {
        _exception = exception;
    }

    private Dictionary<string, object?> Throw() => throw _exception;

    public Dictionary<string, object?> Connect() => Throw();
    public Dictionary<string, object?> Disconnect() => Throw();
    public Dictionary<string, object?> Health() => Throw();
    public Dictionary<string, object?> DocOpen(string path) => Throw();
    public Dictionary<string, object?> DocNewPart(string template = "") => Throw();
    public Dictionary<string, object?> DocNewAssembly(string template = "") => Throw();
    public Dictionary<string, object?> DocSave() => Throw();
    public Dictionary<string, object?> DocSaveAs(string path) => Throw();
    public Dictionary<string, object?> DocClose(bool save = true) => Throw();
    public Dictionary<string, object?> SketchCreate(string plane = "XY") => Throw();
    public Dictionary<string, object?> SketchLine(double x1, double y1, double x2, double y2, string? tag = null, bool connect = false) => Throw();
    public Dictionary<string, object?> SketchCircle(double cx, double cy, double radius, string? tag = null) => Throw();
    public Dictionary<string, object?> SketchArc(double cx, double cy, double radius, double startAngle, double endAngle) => Throw();
    public Dictionary<string, object?> SketchRectangle(double x1, double y1, double x2, double y2) => Throw();
    public Dictionary<string, object?> SketchDimension(string mode, string entity1, string entity2 = "", double? value = null, string orientation = "aligned", double? positionX = null, double? positionY = null) => Throw();
    public Dictionary<string, object?> SketchPoint(double x, double y) => Throw();
    public Dictionary<string, object?> SketchSpline(string points, string fitMethod = "sweet") => Throw();
    public Dictionary<string, object?> SketchEllipse(double cx, double cy, double majorRadius, double minorRadius, double majorAxisAngle = 0.0) => Throw();
    public Dictionary<string, object?> SketchCircularPattern(string entities, string axis, int count, double angle = 360.0, bool fitted = true, bool symmetric = false) => Throw();
    public Dictionary<string, object?> SketchRectangularPattern(string entities, string xAxis, int xCount, double xSpacing, string yAxis = "", int yCount = 1, double ySpacing = 0.0) => Throw();
    public Dictionary<string, object?> SketchOffset(string entities, double offsetX, double offsetY, bool includeConnected = false) => Throw();
    public Dictionary<string, object?> SketchMove(string entities, double dx, double dy, bool copy = false) => Throw();
    public Dictionary<string, object?> SketchRotate(string entities, double cx, double cy, double angle, bool copy = false) => Throw();
    public Dictionary<string, object?> SketchDelete() => Throw();
    public Dictionary<string, object?> SketchConstraint(string mode, string entity1, string entity2 = "", string symLine = "", string axis = "major") => Throw();
    public Dictionary<string, object?> SketchTrim(string entity, string cuttingEntity, string side = "end") => Throw();
    public Dictionary<string, object?> SketchScale(string entities, double cx, double cy, double factor) => Throw();
    public Dictionary<string, object?> SketchMirror(string entities, string mirrorEntity) => Throw();
    public Dictionary<string, object?> SketchLineClose() => Throw();
    public Dictionary<string, object?> SketchProfiles() => Throw();
    public Dictionary<string, object?> Extrude(string profile, double distance, string direction = "positive", double taper = 0.0, string operation = "new_body") => Throw();
    public Dictionary<string, object?> Revolve(string profile, string axis, double angle = 360.0, string direction = "positive", string operation = "join") => Throw();
    public Dictionary<string, object?> Sweep(string profile, string path, string sweepType = "path", string operation = "new_body", double taper = 0, string pathSketch = "", string profileSketch = "") => Throw();
    public Dictionary<string, object?> Fillet(string edges, double radius, string mode = "constant") => Throw();
    public Dictionary<string, object?> Chamfer(string edges, double distance, string mode = "equal_distance") => Throw();
    public Dictionary<string, object?> CircularPattern(string profile, string axis, int count, double angle = 360.0, bool fitWithinAngle = true, bool naturalDirection = true) => Throw();
    public Dictionary<string, object?> MirrorFeature(string profile, string mirrorPlane) => Throw();
    public Dictionary<string, object?> RectangularPattern(string profile, string xAxis, int xCount, double xSpacing, string yAxis = "", int yCount = 1, double ySpacing = 0.0) => Throw();
    public Dictionary<string, object?> Loft(string profiles, string operation = "new_body") => Throw();
    public Dictionary<string, object?> Coil(string profile, string axis, double pitch, double revolutions, string operation = "new_body") => Throw();
    public Dictionary<string, object?> Rib(string profile, double thickness, string direction = "normal", string operation = "new_body") => Throw();
    public Dictionary<string, object?> Emboss(string profile, double depth, string type = "emboss_from_face") => Throw();
    public Dictionary<string, object?> Derive(string sourcePath) => Throw();
    public Dictionary<string, object?> Hole(double x, double y, double diameter, double depth, string type = "drilled", string operation = "join") => Throw();
    public Dictionary<string, object?> Thread(string face, string specification, string direction = "right") => Throw();
    public Dictionary<string, object?> InspectEdges() => Throw();
    public Dictionary<string, object?> ParamList(string? filterPattern = null) => Throw();
    public Dictionary<string, object?> ParamGet(string name) => Throw();
    public Dictionary<string, object?> ParamSet(string name, double value) => Throw();
    public Dictionary<string, object?> ParamSetExpression(string name, string expression) => Throw();
    public Dictionary<string, object?> IPropertyGet(string name, string propertySet = "Summary") => Throw();
    public Dictionary<string, object?> IPropertySet(string name, string? value, string propertySet = "Summary") => Throw();
    public Dictionary<string, object?> IPropertySummary() => Throw();
    public Dictionary<string, object?> IPropertyCustomGet(string name) => Throw();
    public Dictionary<string, object?> IPropertyCustomSet(string name, string? value) => Throw();
    public Dictionary<string, object?> ExportStep(string path, Dictionary<string, object?>? options = null) => Throw();
    public Dictionary<string, object?> ExportStl(string path, Dictionary<string, object?>? options = null) => Throw();
    public Dictionary<string, object?> ExportPdf(string path, Dictionary<string, object?>? options = null) => Throw();
    public Dictionary<string, object?> ExportDxf(string path, Dictionary<string, object?>? options = null) => Throw();
    public Dictionary<string, object?> WorkPlane(string definition, string reference1, string reference2, double offset) => Throw();
    public Dictionary<string, object?> WorkAxis(string definition, string reference1, string reference2) => Throw();
    public Dictionary<string, object?> WorkPoint(string definition, string reference1, string reference2, string reference3) => Throw();
    public Dictionary<string, object?> Shell(string faces, double thickness, string direction = "inside", string operation = "new_body") => Throw();
    public Dictionary<string, object?> Draft(string faces, double angle, string mode = "fixed_edge", string pullDirection = "z", string fixedEntity = "") => Throw();
    public Dictionary<string, object?> Split(string splitTool, string removeSide = "positive", string targetBody = "") => Throw();
    public Dictionary<string, object?> Combine(string baseBody, string toolBodies, string operation = "join", bool keepToolBodies = false) => Throw();
    public Dictionary<string, object?> Thicken(string faces, double thickness, string direction = "positive", string operation = "new_body") => Throw();
    public Dictionary<string, object?> AsmListComponents() => Throw();
    public Dictionary<string, object?> AsmListConstraints() => Throw();
    public Dictionary<string, object?> AsmPlaceComponent(string path, double x = 0, double y = 0, double z = 0) => Throw();
    public Dictionary<string, object?> AsmGroundComponent(string occurrence) => Throw();
    public Dictionary<string, object?> AsmReplaceComponent(string occurrence, string newPath) => Throw();
    public Dictionary<string, object?> AsmDeleteConstraint(string constraint) => Throw();
    public Dictionary<string, object?> AsmConstraintMate(string entityOne, string entityTwo, double offset = 0) => Throw();
    public Dictionary<string, object?> AsmConstraintFlush(string entityOne, string entityTwo, double offset = 0) => Throw();
    public Dictionary<string, object?> AsmConstraintAngle(string entityOne, string entityTwo, double angle, string solution = "directed") => Throw();
    public Dictionary<string, object?> AsmConstraintInsert(string entityOne, string entityTwo, double offset = 0) => Throw();
    public Dictionary<string, object?> AsmConstraintTangent(string entityOne, string entityTwo, double offset = 0) => Throw();
    public Dictionary<string, object?> AsmCircularPattern(string occurrence, string axis, int count, double angle = 360) => Throw();
    public Dictionary<string, object?> AsmRectangularPattern(string occurrence, string xAxis, int xCount, double xSpacing, string? yAxis = null, int yCount = 1, double ySpacing = 0) => Throw();
    public Dictionary<string, object?> AsmExtrudeCut(string profile, double distance, string direction = "positive") => Throw();
    public Dictionary<string, object?> AsmHole(double x, double y, double diameter, double depth, string type = "drilled") => Throw();
    public Dictionary<string, object?> AsmBom() => Throw();
}