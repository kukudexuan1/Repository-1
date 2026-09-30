namespace McpCad.Tests.Integration;

using McpCad.Inventor;
using McpCad.Inventor.Managers;

[Collection("Inventor integration")]
public class SketchIntegrationTests
{
    private static (InventorDriver Driver, DocumentManager Document, SketchManager Sketch) NewPart()
    {
        var driver = new InventorDriver();
        Assert.True((bool)driver.Connect()["connected"]!);
        var document = new DocumentManager(driver);
        Assert.True((bool)document.DocNewPart()["success"]!);
        return (driver, document, new SketchManager(driver));
    }

    private static void Close(InventorDriver driver, DocumentManager document)
    {
        document.DocClose(false);
        driver.Disconnect();
    }

    [InventorFact]
    public void SketchCreate_OnXYPlane_ReturnsNumericFrame()
    {
        var (driver, document, sketch) = NewPart();
        var result = sketch.SketchCreate("XY");
        Assert.True((bool)result["success"]!);
        var frame = Assert.IsType<Dictionary<string, object?>>(result["sketch_frame"]);
        Assert.Equal(3, Assert.IsType<double[]>(frame["origin"]).Length);
        Assert.Equal(3, Assert.IsType<double[]>(frame["u"]).Length);
        Assert.Equal(3, Assert.IsType<double[]>(frame["v"]).Length);
        Close(driver, document);
    }

    [InventorFact]
    public void SketchLine_DrawsLine_InActiveSketch()
    {
        var (driver, document, sketch) = NewPart();
        Assert.True((bool)sketch.SketchCreate("XY")["success"]!);
        Assert.True((bool)sketch.SketchLine(0, 0, 2, 0)["success"]!);
        dynamic compDef = driver.ComponentDefinition!;
        Assert.Equal(1, (int)compDef.Sketches.Item(1).SketchLines.Count);
        Close(driver, document);
    }

    [InventorFact]
    public void SketchCircle_WithTag_StoresResolvableEntity()
    {
        var (driver, document, sketch) = NewPart();
        Assert.True((bool)sketch.SketchCreate("XY")["success"]!);
        Assert.True((bool)sketch.SketchCircle(0, 0, 1, "golden_circle")["success"]!);
        dynamic compDef = driver.ComponentDefinition!;
        Assert.Equal(1, (int)compDef.Sketches.Item(1).SketchCircles.Count);
        Close(driver, document);
    }

    [InventorFact]
    public void SketchLine_ConnectMode_ChainsEndpoints()
    {
        var (driver, document, sketch) = NewPart();
        Assert.True((bool)sketch.SketchCreate("XY")["success"]!);
        sketch.SketchLine(0, 0, 1, 0, connect: true);
        sketch.SketchLine(99, 99, 1, 1, connect: true);
        dynamic lines = driver.ComponentDefinition!.Sketches.Item(1).SketchLines;
        dynamic firstEnd = lines.Item(1).EndSketchPoint;
        dynamic secondStart = lines.Item(2).StartSketchPoint;
        Assert.Equal((double)firstEnd.Geometry.X, (double)secondStart.Geometry.X, 6);
        Assert.Equal((double)firstEnd.Geometry.Y, (double)secondStart.Geometry.Y, 6);
        Close(driver, document);
    }

    [InventorFact]
    public void SketchOffset_WithWrappedEntities_Succeeds()
    {
        var (driver, document, sketch) = NewPart();
        Assert.True((bool)sketch.SketchCreate("XY")["success"]!);
        Assert.True((bool)sketch.SketchCircle(0, 0, 3)["success"]!);
        var result = sketch.SketchOffset("1", 5, 0);
        Assert.True((bool)result["success"]!, result.GetValueOrDefault("error")?.ToString());
        Assert.Equal("offset", result["operation"]);
        Close(driver, document);
    }
}
