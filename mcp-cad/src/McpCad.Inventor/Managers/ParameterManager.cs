using McpCad.Core.Exceptions;
using McpCad.Core.Models;
using InvApp = Inventor.Application;

namespace McpCad.Inventor.Managers;

/// <summary>
/// Manages Inventor model parameters: list, get, set, and expressions.
/// Accesses ComponentDefinition.Parameters via COM.
/// </summary>
public class ParameterManager(InventorDriver driver)
{
    private InvApp App => driver.InventorApp;

    private dynamic ComponentDefinition()
    {
        return driver.ComponentDefinition
            ?? throw new InventorComException("No component definition available. Open a document first.");
    }

    /// <summary>
    /// List model parameters, optionally filtered by name pattern (case-insensitive substring).
    /// </summary>
    public Dictionary<string, object?> ParamList(string? filter = null)
    {
        try
        {
            var compDef = ComponentDefinition();
            dynamic parameters = compDef.Parameters;

            var result = new List<Dictionary<string, object?>>();
            int count = parameters.Count;

            for (int i = 1; i <= count; i++)
            {
                dynamic param = parameters.Item(i);
                string name = param.Name;

                // Apply case-insensitive filter
                if (filter is not null && !name.Contains(filter, StringComparison.OrdinalIgnoreCase))
                    continue;

                result.Add(new Dictionary<string, object?>
                {
                    ["name"] = name,
                    ["value"] = param.Value,
                    ["expression"] = param.Expression,
                });
            }

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["parameters"] = result,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to list parameters: {ex.Message}", ex); }
    }

    /// <summary>
    /// Get a specific parameter by name (case-sensitive, as Inventor stores it).
    /// </summary>
    public Dictionary<string, object?> ParamGet(string name)
    {
        try
        {
            var compDef = ComponentDefinition();
            dynamic parameters = compDef.Parameters;
            dynamic param = parameters.Item(name);

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["name"] = param.Name,
                ["value"] = param.Value,
                ["expression"] = param.Expression,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to get parameter '{name}': {ex.Message}", ex); }
    }

    /// <summary>
    /// Set a parameter value by name.
    /// </summary>
    public Dictionary<string, object?> ParamSet(string name, double value)
    {
        try
        {
            var compDef = ComponentDefinition();
            dynamic parameters = compDef.Parameters;
            dynamic param = parameters.Item(name);
            param.Value = value;

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["name"] = name,
                ["value"] = param.Value,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to set parameter '{name}': {ex.Message}", ex); }
    }

    /// <summary>
    /// Set a parameter using an Inventor expression (e.g., "d0 * 2").
    /// </summary>
    public Dictionary<string, object?> ParamSetExpression(string name, string expression)
    {
        try
        {
            var compDef = ComponentDefinition();
            dynamic parameters = compDef.Parameters;
            dynamic param = parameters.Item(name);
            param.Expression = expression;

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["name"] = name,
                ["expression"] = param.Expression,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to set expression for parameter '{name}': {ex.Message}", ex); }
    }
}