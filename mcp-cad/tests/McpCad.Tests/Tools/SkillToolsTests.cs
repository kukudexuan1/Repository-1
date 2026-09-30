using McpCad.Tests.Mocks;
using McpCad.Tools;

namespace McpCad.Tests.Tools;

public class SkillToolsTests
{
    private readonly MockInventorProvider _mock = new();
    private readonly SkillTools _tools;

    public SkillToolsTests()
    {
        _tools = new SkillTools(_mock);
    }

    private bool WasCalled(string methodName)
        => _mock.CallLog.Any(c => c.Method == methodName);

    // ── Drawing skills ────────────────────────────────────────────────

    [Fact]
    public void SkillSketch_CreatesSketch()
    {
        var result = _tools.skill_sketch("XY");

        Assert.True((bool)result["success"]!);
        Assert.True(WasCalled("SketchCreate"));
    }

    [Fact]
    public void SkillLine_SimpleMode_DelegatesCorrectly()
    {
        var result = _tools.skill_line(mode: "simple", start_x: 0, start_y: 0, end_x: 10, end_y: 5);

        Assert.True((bool)result["success"]!);
        Assert.True(WasCalled("SketchLine"));
    }

    [Fact]
    public void SkillLine_MidpointMode_ComputesOppositeEndpoint()
    {
        var result = _tools.skill_line(mode: "midpoint", mid_x: 5, mid_y: 5, end_x: 10, end_y: 5);

        Assert.True((bool)result["success"]!);
        var lineCall = _mock.CallLog.First(c => c.Method == "SketchLine");
        Assert.Equal(0.0, lineCall.Args["x1"]);
        Assert.Equal(5.0, lineCall.Args["y1"]);
        Assert.Equal(10.0, lineCall.Args["x2"]);
        Assert.Equal(5.0, lineCall.Args["y2"]);
    }

    [Fact]
    public void SkillLine_InvalidMode_ReturnsError()
    {
        var result = _tools.skill_line(mode: "invalid");

        Assert.False((bool)result["success"]!);
        Assert.Contains("Unknown mode", result["error"]!.ToString());
    }

    [Fact]
    public void SkillCircle_CenterMode_DelegatesCorrectly()
    {
        var result = _tools.skill_circle(mode: "center", cx: 5, cy: 5, radius: 3);

        Assert.True((bool)result["success"]!);
        Assert.True(WasCalled("SketchCircle"));
    }

    [Fact]
    public void SkillCircle_InvalidMode_ReturnsError()
    {
        var result = _tools.skill_circle(mode: "invalid");

        Assert.False((bool)result["success"]!);
    }

    [Fact]
    public void SkillArc_SweepMode_DelegatesCorrectly()
    {
        var result = _tools.skill_arc(mode: "sweep", cx: 0, cy: 0, radius: 5, start_angle: 0, sweep_angle: 90);

        Assert.True((bool)result["success"]!);
    }

    [Fact]
    public void SkillRect_DiagonalMode_DelegatesCorrectly()
    {
        var result = _tools.skill_rect(mode: "diagonal", x1: 0, y1: 0, x2: 10, y2: 10);

        Assert.True((bool)result["success"]!);
    }

    [Fact]
    public void SkillRect_CenterMode_ComputesOppositeCorner()
    {
        var result = _tools.skill_rect(mode: "center", cx: 5, cy: 5, corner_x: 10, corner_y: 10);

        Assert.True((bool)result["success"]!);
        var rectCall = _mock.CallLog.First(c => c.Method == "SketchRectangle");
        Assert.Equal(10.0, rectCall.Args["x1"]);
        Assert.Equal(10.0, rectCall.Args["y1"]);
        Assert.Equal(0.0, rectCall.Args["x2"]);
        Assert.Equal(0.0, rectCall.Args["y2"]);
    }

    [Fact]
    public void SkillPoint_DelegatesCorrectly()
    {
        var result = _tools.skill_point(x: 5, y: 10);
        Assert.True((bool)result["success"]!);
    }

    [Fact]
    public void SkillEllipse_DelegatesCorrectly()
    {
        var result = _tools.skill_ellipse(cx: 0, cy: 0, major_radius: 5, minor_radius: 3);
        Assert.True((bool)result["success"]!);
    }

    [Fact]
    public void SkillSpline_EmptyPoints_ReturnsError()
    {
        var result = _tools.skill_spline(points: "");

        Assert.False((bool)result["success"]!);
        Assert.Contains("at least 3 points", result["error"]!.ToString());
    }

    [Fact]
    public void SkillSpline_ValidPoints_DelegatesCorrectly()
    {
        var result = _tools.skill_spline(points: "0,0,5,5,10,0");
        Assert.True((bool)result["success"]!);
    }

    // ── Pattern skills ────────────────────────────────────────────────

    [Fact]
    public void SkillPatternCircular_DelegatesCorrectly()
    {
        var result = _tools.skill_pattern_circular(entities: "1", axis: "2", count: 6);
        Assert.True((bool)result["success"]!);
    }

    [Fact]
    public void SkillPatternRectangular_DelegatesCorrectly()
    {
        var result = _tools.skill_pattern_rectangular(entities: "1", x_axis: "2", x_count: 3, x_spacing: 5);
        Assert.True((bool)result["success"]!);
    }

    // ── Modify skills ─────────────────────────────────────────────────

    [Fact]
    public void SkillMove_DelegatesCorrectly()
    {
        var result = _tools.skill_move(entities: "1", dx: 10, dy: 5);
        Assert.True((bool)result["success"]!);
    }

    [Fact]
    public void SkillRotate_DelegatesCorrectly()
    {
        var result = _tools.skill_rotate(entities: "1", cx: 0, cy: 0, angle: 90);
        Assert.True((bool)result["success"]!);
    }

    [Fact]
    public void SkillScale_DelegatesCorrectly()
    {
        var result = _tools.skill_scale(entities: "1", cx: 0, cy: 0, factor: 2);
        Assert.True((bool)result["success"]!);
    }

    [Fact]
    public void SkillOffset_DelegatesCorrectly()
    {
        var result = _tools.skill_offset(entities: "1", offset_x: 0, offset_y: 5);
        Assert.True((bool)result["success"]!);
    }

    [Fact]
    public void SkillMirror_DelegatesCorrectly()
    {
        var result = _tools.skill_mirror(entities: "1", mirror_entity: "2");
        Assert.True((bool)result["success"]!);
    }

    [Fact]
    public void SkillTrim_DelegatesCorrectly()
    {
        var result = _tools.skill_trim(entity: "1", cutting_entity: "2");
        Assert.True((bool)result["success"]!);
    }

    // ── Constraint + dimension skills ─────────────────────────────────

    [Fact]
    public void SkillConstraint_DelegatesCorrectly()
    {
        var result = _tools.skill_constraint(mode: "parallel", entity1: "1", entity2: "2");
        Assert.True((bool)result["success"]!);
    }

    [Fact]
    public void SkillDimension_DelegatesCorrectly()
    {
        var result = _tools.skill_dimension(mode: "radius", entity1: "1", value: 5);
        Assert.True((bool)result["success"]!);
    }

    // ── Revolve skill ───────────────────────────────────────────────────

    [Fact]
    public void SkillRevolve_AutoDraw_CallsMultipleProviderMethods()
    {
        var result = _tools.skill_revolve(profile: "", profile_cx: 3, profile_radius: 1);

        Assert.True(WasCalled("SketchCreate"));
        Assert.True(WasCalled("SketchCircle"));
        Assert.True(WasCalled("SketchLine"));
        Assert.True(WasCalled("Revolve"));
    }

    [Fact]
    public void SkillRevolve_WithExistingProfile_SkipsSketchAndCircle()
    {
        var result = _tools.skill_revolve(profile: "1", axis_x: 0);

        Assert.False(WasCalled("SketchCreate"));
        Assert.False(WasCalled("SketchCircle"));
        Assert.True(WasCalled("SketchLine"));
        Assert.True(WasCalled("Revolve"));
    }

    // ── Delete sketch skill ────────────────────────────────────────────

    [Fact]
    public void SkillDeleteSketch_DelegatesCorrectly()
    {
        var result = _tools.skill_delete_sketch();

        Assert.True((bool)result["success"]!);
        Assert.True(WasCalled("SketchDelete"));
    }

    // ── CircleFromThreePoints helper tests ─────────────────────────────

    [Fact]
    public void SkillCircle_3PointMode_ComputesCircle()
    {
        var result = _tools.skill_circle(
            mode: "3point",
            x1: 5, y1: 0,
            x2: 0, y2: 5,
            x3: -5, y3: 0);

        Assert.True((bool)result["success"]!);
        Assert.True(WasCalled("SketchCircle"));
    }
}