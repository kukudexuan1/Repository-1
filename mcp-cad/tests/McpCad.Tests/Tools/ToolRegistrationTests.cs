using McpCad.Core;
using McpCad.Core.Exceptions;
using McpCad.Tests.Mocks;
using McpCad.Tools;
using System.ComponentModel;
using Microsoft.Extensions.DependencyInjection;
using ModelContextProtocol.Server;
using System.Reflection;

namespace McpCad.Tests.Tools;

public class ToolRegistrationTests
{
    /// <summary>
    /// Verifies that every public method on AtomicTools has the [McpServerTool] attribute.
    /// </summary>
    [Fact]
    public void AtomicTools_AllMethods_HaveMcpServerToolAttribute()
    {
        var methods = typeof(AtomicTools).GetMethods(BindingFlags.Public | BindingFlags.Instance)
            .Where(m => m.DeclaringType == typeof(AtomicTools))
            .ToList();

        Assert.NotEmpty(methods);

        foreach (var method in methods)
        {
            var attr = method.GetCustomAttribute<McpServerToolAttribute>();
            Assert.True(attr is not null,
                $"Method '{method.Name}' on AtomicTools is missing [McpServerTool] attribute.");
        }
    }

    /// <summary>
    /// Verifies that every public method on SkillTools has the [McpServerTool] attribute.
    /// </summary>
    [Fact]
    public void SkillTools_AllMethods_HaveMcpServerToolAttribute()
    {
        var methods = typeof(SkillTools).GetMethods(BindingFlags.Public | BindingFlags.Instance)
            .Where(m => m.DeclaringType == typeof(SkillTools))
            .ToList();

        Assert.NotEmpty(methods);

        foreach (var method in methods)
        {
            var attr = method.GetCustomAttribute<McpServerToolAttribute>();
            Assert.True(attr is not null,
                $"Method '{method.Name}' on SkillTools is missing [McpServerTool] attribute.");
        }
    }

    /// <summary>
    /// Verifies AtomicTools has the [McpServerToolType] attribute.
    /// </summary>
    [Fact]
    public void AtomicTools_HasMcpServerToolTypeAttribute()
    {
        var attr = typeof(AtomicTools).GetCustomAttribute<McpServerToolTypeAttribute>();
        Assert.NotNull(attr);
    }

    /// <summary>
    /// Verifies SkillTools has the [McpServerToolType] attribute.
    /// </summary>
    [Fact]
    public void SkillTools_HasMcpServerToolTypeAttribute()
    {
        var attr = typeof(SkillTools).GetCustomAttribute<McpServerToolTypeAttribute>();
        Assert.NotNull(attr);
    }

    /// <summary>
    /// Verifies AtomicTools methods have [Description] attributes for MCP schema.
    /// </summary>
    [Fact]
    public void AtomicTools_AllMethods_HaveDescriptionAttribute()
    {
        var methods = typeof(AtomicTools).GetMethods(BindingFlags.Public | BindingFlags.Instance)
            .Where(m => m.DeclaringType == typeof(AtomicTools))
            .ToList();

        foreach (var method in methods)
        {
            var desc = method.GetCustomAttribute<DescriptionAttribute>();
            Assert.True(desc is not null,
                $"Method '{method.Name}' on AtomicTools is missing [Description] attribute.");
            Assert.False(string.IsNullOrWhiteSpace(desc!.Description),
                $"Method '{method.Name}' has an empty [Description].");
        }
    }

    /// <summary>
    /// Verifies SkillTools methods have [Description] attributes.
    /// </summary>
    [Fact]
    public void SkillTools_AllMethods_HaveDescriptionAttribute()
    {
        var methods = typeof(SkillTools).GetMethods(BindingFlags.Public | BindingFlags.Instance)
            .Where(m => m.DeclaringType == typeof(SkillTools))
            .ToList();

        foreach (var method in methods)
        {
            var desc = method.GetCustomAttribute<DescriptionAttribute>();
            Assert.True(desc is not null,
                $"Method '{method.Name}' on SkillTools is missing [Description] attribute.");
        }
    }

    /// <summary>
    /// Verifies DI wiring: register mock provider and AtomicTools, verify resolution.
    /// </summary>
    [Fact]
    public void DI_Registration_ResolvesAtomicTools()
    {
        var mock = new MockInventorProvider();
        var services = new ServiceCollection();
        services.AddSingleton<IMechanicalCadProvider>(mock);
        services.AddSingleton<AtomicTools>();

        var provider = services.BuildServiceProvider();
        var tools = provider.GetService<AtomicTools>();

        Assert.NotNull(tools);
        Assert.IsType<AtomicTools>(tools);
    }

    /// <summary>
    /// Verifies DI wiring for SkillTools.
    /// </summary>
    [Fact]
    public void DI_Registration_ResolvesSkillTools()
    {
        var mock = new MockInventorProvider();
        var services = new ServiceCollection();
        services.AddSingleton<IMechanicalCadProvider>(mock);
        services.AddSingleton<SkillTools>();

        var provider = services.BuildServiceProvider();
        var tools = provider.GetService<SkillTools>();

        Assert.NotNull(tools);
        Assert.IsType<SkillTools>(tools);
    }

    /// <summary>
    /// Verifies that the resolved tool uses the registered provider.
    /// </summary>
    [Fact]
    public void DI_Registration_InjectsCorrectProvider()
    {
        var mock = new MockInventorProvider();
        var services = new ServiceCollection();
        services.AddSingleton<IMechanicalCadProvider>(mock);
        services.AddSingleton<AtomicTools>();

        var provider = services.BuildServiceProvider();
        var tools = provider.GetRequiredService<AtomicTools>();

        var result = tools.inventor_health();
        Assert.True((bool)result["success"]!);
    }

    /// <summary>
    /// Verifies the count of atomic tool methods is reasonable.
    /// </summary>
    [Fact]
    public void AtomicTools_HasExpectedMethodCount()
    {
        var methods = typeof(AtomicTools).GetMethods(BindingFlags.Public | BindingFlags.Instance)
            .Where(m => m.DeclaringType == typeof(AtomicTools))
            .ToList();

        Assert.True(methods.Count >= 48,
            $"Expected at least 48 tool methods on AtomicTools, found {methods.Count}");
    }

    /// <summary>
    /// Verifies ToolHelpers.Error produces correct error shape.
    /// </summary>
    [Fact]
    public void ToolHelpers_Error_Returns_CorrectShape()
    {
        var result = ToolHelpers.Error("Something went wrong");

        Assert.False((bool)result["success"]!);
        Assert.Equal("Something went wrong", result["error"]);
        Assert.Equal(2, result.Count);
    }

    /// <summary>
    /// Verifies ToolHelpers.Ok returns success with optional data.
    /// </summary>
    [Fact]
    public void ToolHelpers_Ok_Returns_CorrectShape()
    {
        var result = ToolHelpers.Ok();

        Assert.True((bool)result["success"]!);
        Assert.Single(result);
    }

    [Fact]
    public void ToolHelpers_Ok_WithExtra_MergesData()
    {
        var result = ToolHelpers.Ok(new Dictionary<string, object?>
        {
            ["feature"] = "Extrusion1",
            ["distance"] = 5.0,
        });

        Assert.True((bool)result["success"]!);
        Assert.Equal("Extrusion1", result["feature"]);
        Assert.Equal(5.0, result["distance"]);
    }
}