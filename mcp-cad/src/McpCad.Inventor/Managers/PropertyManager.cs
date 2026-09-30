using McpCad.Core.Exceptions;
using McpCad.Core.Models;
using InvApp = Inventor.Application;

namespace McpCad.Inventor.Managers;

/// <summary>
/// Manages Inventor iProperties: read, write, summary, and custom.
/// Standard iProperties via PropertySets, custom via Design Tracking Properties.
/// </summary>
public class PropertyManager(InventorDriver driver)
{
    // Inventor iProperty set COM identifiers (1-based lookup names)
    private const string SummaryPropertySet = "Inventor Summary Information";
    private const string ProjectPropertySet = "Inventor Document Summary Information";
    private const string CustomPropertySet = "Design Tracking Properties";

    private InvApp App => driver.InventorApp;

    private dynamic ActiveDocument()
    {
        var doc = driver.ActiveDocument
            ?? throw new InventorComException("No active document. Open or create a document first.");
        return doc;
    }

    /// <summary>
    /// Map a friendly property-set name to the Inventor COM identifier.
    /// </summary>
    private static string ResolvePropertySet(string propSet)
    {
        return propSet.ToLowerInvariant() switch
        {
            "summary" => SummaryPropertySet,
            "project" => ProjectPropertySet,
            "custom" => CustomPropertySet,
            _ => throw new InventorComException(
                $"Invalid property set '{propSet}'. Must be one of: summary, project, custom.")
        };
    }

    /// <summary>
    /// Get an iProperty value by name from the specified property set.
    /// </summary>
    public Dictionary<string, object?> IPropertyGet(string name, string propSet = "Summary")
    {
        try
        {
            var doc = ActiveDocument();
            string setKey = ResolvePropertySet(propSet);
            dynamic propertySets = doc.PropertySets;
            dynamic propSetObj = propertySets.Item(setKey);
            dynamic prop = propSetObj.Item(name);

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["name"] = name,
                ["value"] = prop.Value,
                ["property_set"] = propSet,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to get iProperty '{name}': {ex.Message}", ex); }
    }

    /// <summary>
    /// Set an iProperty value by name in the specified property set.
    /// </summary>
    public Dictionary<string, object?> IPropertySet(string name, string? value, string propSet = "Summary")
    {
        try
        {
            var doc = ActiveDocument();
            string setKey = ResolvePropertySet(propSet);
            dynamic propertySets = doc.PropertySets;
            dynamic propSetObj = propertySets.Item(setKey);
            dynamic prop = propSetObj.Item(name);
            prop.Value = value;

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["name"] = name,
                ["value"] = value,
                ["property_set"] = propSet,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to set iProperty '{name}': {ex.Message}", ex); }
    }

    /// <summary>
    /// Get all properties from the Summary iProperty set.
    /// </summary>
    public Dictionary<string, object?> IPropertySummary()
    {
        try
        {
            var doc = ActiveDocument();
            dynamic propertySets = doc.PropertySets;
            dynamic propSetObj = propertySets.Item(SummaryPropertySet);

            var result = new List<Dictionary<string, object?>>();
            int count = propSetObj.Count;

            for (int i = 1; i <= count; i++)
            {
                dynamic prop = propSetObj.Item(i);
                result.Add(new Dictionary<string, object?>
                {
                    ["name"] = prop.Name,
                    ["value"] = prop.Value,
                });
            }

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["properties"] = result,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to get summary iProperties: {ex.Message}", ex); }
    }

    /// <summary>
    /// Get a custom iProperty by name from the Design Tracking Properties set.
    /// </summary>
    public Dictionary<string, object?> IPropertyCustomGet(string name)
    {
        try
        {
            var doc = ActiveDocument();
            dynamic propertySets = doc.PropertySets;
            dynamic propSetObj = propertySets.Item(CustomPropertySet);
            dynamic prop = propSetObj.Item(name);

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["name"] = prop.Name,
                ["value"] = prop.Value,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to get custom iProperty '{name}': {ex.Message}", ex); }
    }

    /// <summary>
    /// Set a custom iProperty. Creates it if it doesn't exist.
    /// </summary>
    public Dictionary<string, object?> IPropertyCustomSet(string name, string? value)
    {
        try
        {
            var doc = ActiveDocument();
            dynamic propertySets = doc.PropertySets;
            dynamic propSetObj = propertySets.Item(CustomPropertySet);

            try
            {
                // Property exists — update it
                dynamic prop = propSetObj.Item(name);
                prop.Value = value;
            }
            catch
            {
                // Property doesn't exist — create it
                propSetObj.Add(name, value);
            }

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["name"] = name,
                ["value"] = value,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to set custom iProperty '{name}': {ex.Message}", ex); }
    }
}