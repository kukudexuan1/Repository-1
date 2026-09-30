namespace McpCad.Tests.Integration;

using McpCad.Inventor;
using McpCad.Inventor.Managers;

[Collection("Inventor integration")]
public class ComConnectionTests
{
    [InventorFact]
    public void Connect_ToRunningInventor_ReturnsSuccess()
    {
        var driver = new InventorDriver();
        var result = driver.Connect();

        Assert.True((bool)result["connected"]!, result.GetValueOrDefault("error")?.ToString());
        Assert.True(driver.IsConnected);
        driver.Disconnect();
    }

    [InventorFact]
    public void Health_WithActiveDocument_ReturnsVersion()
    {
        var driver = new InventorDriver();
        Assert.True((bool)driver.Connect()["connected"]!);
        var document = new DocumentManager(driver);
        Assert.True((bool)document.DocNewPart()["success"]!);

        var health = driver.Health();

        Assert.True((bool)health["connected"]!);
        Assert.False(string.IsNullOrWhiteSpace(health["inventor_version"]?.ToString()));
        Assert.NotNull(health["active_document"]);
        document.DocClose(false);
        driver.Disconnect();
    }

    [InventorFact]
    public void Disconnect_ReleasesCOM_Resources()
    {
        var driver = new InventorDriver();
        Assert.True((bool)driver.Connect()["connected"]!);

        var result = driver.Disconnect();

        Assert.Equal("disconnected", result["status"]);
        Assert.False(driver.IsConnected);
        Assert.False((bool)driver.Health()["connected"]!);
    }
}
