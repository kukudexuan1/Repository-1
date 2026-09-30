namespace McpCad.Tests.Integration;

using McpCad.Inventor;
using McpCad.Inventor.Managers;

[Collection("Inventor integration")]
public class FeatureIntegrationTests
{
    private static (InventorDriver Driver, DocumentManager Document) NewPart()
    {
        var driver = new InventorDriver();
        Assert.True((bool)driver.Connect()["connected"]!);
        var document = new DocumentManager(driver);
        Assert.True((bool)document.DocNewPart()["success"]!);
        return (driver, document);
    }

    private static void Close(InventorDriver driver, DocumentManager document)
    {
        document.DocClose(false);
        driver.Disconnect();
    }

    private static double AxisSize(Dictionary<string, object?> boundingBox, string axis)
    {
        var size = boundingBox["size"]!;
        return Convert.ToDouble(size.GetType().GetProperty(axis)!.GetValue(size));
    }

    [InventorFact]
    public void Extrude_Profile_CreatesSingleSolidWithExpectedExtent()
    {
        var (driver, document) = NewPart();
        var sketch = new SketchManager(driver);
        Assert.True((bool)sketch.SketchCreate("XY")["success"]!);
        Assert.True((bool)sketch.SketchRectangle(0, 0, 2, 3)["success"]!);
        var result = new FeatureManager(driver).Extrude("1", 5, operation: "new_body");
        Assert.True((bool)result["success"]!, result.GetValueOrDefault("error")?.ToString());
        var inspection = new InspectionManager(driver);
        Assert.Equal(1, inspection.GetBodyCount()["body_count"]);
        var boundingBox = inspection.GetBoundingBox("model");
        var extents = new[]
        {
            AxisSize(boundingBox, "x"),
            AxisSize(boundingBox, "y"),
            AxisSize(boundingBox, "z"),
        }.OrderBy(value => value).ToArray();
        Assert.Equal(2, extents[0], 3);
        Assert.Equal(3, extents[1], 3);
        Assert.Equal(5, extents[2], 3);
        Close(driver, document);
    }

    [InventorFact]
    public void Revolve_FixedGolden_RepeatsStableGeometry()
    {
        for (var run = 0; run < 3; run++)
        {
            var (driver, document) = NewPart();
            var deterministic = new DeterministicFeatureManager(driver);
            var result = deterministic.CreateRevolvedProfile(
                $"golden_shaft_{run}",
                "X",
                "[[0,0],[0,1],[5,1],[5,0]]");
            Assert.True((bool)result["success"]!, result.GetValueOrDefault("error")?.ToString());
            var inspection = new InspectionManager(driver);
            Assert.Equal(1, inspection.GetBodyCount()["body_count"]);
            var boundingBox = inspection.GetBoundingBox("model");
            Assert.Equal(5, AxisSize(boundingBox, "x"), 3);
            Assert.Equal(2, AxisSize(boundingBox, "y"), 3);
            Assert.Equal(2, AxisSize(boundingBox, "z"), 3);
            Close(driver, document);
        }
    }

    [InventorFact]
    public void Fillet_Edges_CreatesConstantRadiusFillet()
    {
        var (driver, document) = NewPart();
        var sketch = new SketchManager(driver);
        sketch.SketchCreate("XY");
        sketch.SketchRectangle(0, 0, 2, 2);
        new FeatureManager(driver).Extrude("1", 2, operation: "new_body");
        var result = new FeatureManager(driver).Fillet("1", 0.2);
        Assert.True((bool)result["success"]!, result.GetValueOrDefault("error")?.ToString());
        Close(driver, document);
    }

    [InventorFact]
    public void Hole_AtPosition_CreatesDrilledHole()
    {
        var (driver, document) = NewPart();
        var sketch = new SketchManager(driver);
        sketch.SketchCreate("XY");
        sketch.SketchRectangle(-2, -2, 2, 2);
        var features = new FeatureManager(driver);
        features.Extrude("1", 2, operation: "new_body");
        var result = features.Hole(0, 0, 0.5, 1);
        Assert.True((bool)result["success"]!, result.GetValueOrDefault("error")?.ToString());
        Close(driver, document);
    }
}
