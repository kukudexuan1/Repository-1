// SPDX-License-Identifier: GPL-3.0-only
//
// Added by kukudexuan1 (2026) as part of the modified mcp-cad distribution.
// Based on mcp-cad (https://github.com/Andiveli/mcp-cad), licensed under GNU GPL v3.0.
// See the LICENSE file in the mcp-cad directory for the full license text.

using System.Text.Json;
using McpCad.Core.Models;

namespace McpCad.Inventor.Managers;

public class DeterministicFeatureManager
{
    private readonly SketchManager _sketch;
    private readonly FeatureManager _feature;
    private readonly InspectionManager _inspection;
    private readonly WorkFeatureManager _work;
    private readonly InventorDriver _driver;

    public DeterministicFeatureManager(InventorDriver driver)
    {
        _driver = driver;
        _sketch = new SketchManager(driver);
        _feature = new FeatureManager(driver);
        _inspection = new InspectionManager(driver);
        _work = new WorkFeatureManager(driver);
    }

    public Dictionary<string, object?> CreateRevolvedProfile(string name, string mainAxis, string profilePointsJson)
    {
        try
        {
            var points = JsonSerializer.Deserialize<double[][]>(profilePointsJson) ?? [];
            if (points.Length < 4) return ErrorResult.Create("profile_points_json needs at least four [axis,radius] points.");
            string axis = mainAxis.ToUpperInvariant();
            string plane = axis switch { "X" => "XY", "Y" => "YZ", "Z" => "XZ", _ => "" };
            if (plane == "") return ErrorResult.Create("main_axis must be X, Y, or Z.");
            bool axisOnSketchX = axis != "Z";
            var sketchResult = _sketch.SketchCreate(plane);
            if (!Succeeded(sketchResult)) return sketchResult;
            double min = points.Min(p => p[0]);
            double max = points.Max(p => p[0]);
            if (axisOnSketchX) _sketch.SketchLine(min, 0, max, 0, "axis_main", false, true);
            else _sketch.SketchLine(0, min, 0, max, "axis_main", false, true);
            for (int i = 0; i < points.Length; i++)
            {
                double[] a = points[i];
                double[] b = points[(i + 1) % points.Length];
                if (axisOnSketchX) _sketch.SketchLine(a[0], a[1], b[0], b[1], null, i > 0, false);
                else _sketch.SketchLine(a[1], a[0], b[1], b[0], null, i > 0, false);
            }
            var result = _feature.Revolve("1", "@axis_main", 360.0, "positive", "new_body");
            if (!Succeeded(result)) return result;
            dynamic compDef = _driver.ComponentDefinition!;
            dynamic revolutions = compDef.Features.RevolveFeatures;
            revolutions.Item(revolutions.Count).Name = name;
            result["semantic_name"] = name;
            result["main_axis"] = mainAxis.ToUpperInvariant();
            result["body_count"] = _inspection.GetBodyCount()["body_count"];
            return result;
        }
        catch (Exception ex) { return ErrorResult.Create($"Deterministic revolve failed: {ex.Message}"); }
    }

    public Dictionary<string, object?> CutKeyway(
        string name, string mainAxis, string targetSegment,
        double segmentStartCm, double segmentEndCm, double segmentDiameterCm,
        double axisStartCm, double axisEndCm, string radialDirection,
        double lengthCm, double widthCm, double depthCm)
    {
        if (axisStartCm < segmentStartCm || axisEndCm > segmentEndCm)
            return ErrorResult.Create("Keyway range is outside target segment.");
        if (depthCm <= 0 || depthCm >= segmentDiameterCm / 2)
            return ErrorResult.Create("Keyway depth must be positive and less than segment radius.");
        string radial = radialDirection.ToUpperInvariant();
        string axis = mainAxis.ToUpperInvariant();
        if (axis != "X") return ErrorResult.Create("cut_keyway currently supports X-axis shafts; choose lower-level sketch/cut tools for other axes.");
        string plane = radial.EndsWith("Z") ? "XY" : radial.EndsWith("Y") ? "XZ" : "";
        if (plane == "" || radial.EndsWith(mainAxis.ToUpperInvariant()))
            return ErrorResult.Create("Keyway radial direction must be perpendicular to main axis.");
        double sign = radial.StartsWith("-") ? -1 : 1;
        var workPlane = _work.WorkPlane("offset_from_plane", plane, "", sign * segmentDiameterCm / 2);
        if (!Succeeded(workPlane)) return workPlane;
        var planeInfo = (Dictionary<string, object?>)workPlane["plane"]!;
        var sketchResult = _sketch.SketchCreate((string)planeInfo["name"]!);
        if (!Succeeded(sketchResult)) return sketchResult;
        double center = (axisStartCm + axisEndCm) / 2;
        _sketch.SketchRectangle(center - lengthCm / 2, -widthCm / 2, center + lengthCm / 2, widthCm / 2);
        var result = _feature.Extrude("1", depthCm, sign > 0 ? "negative" : "positive", 0, "cut");
        if (!Succeeded(result)) return result;
        dynamic compDef = _driver.ComponentDefinition!;
        dynamic extrudes = compDef.Features.ExtrudeFeatures;
        extrudes.Item(extrudes.Count).Name = name;
        result["semantic_name"] = name;
        result["target_segment"] = targetSegment;
        result["radial_direction"] = radial;
        result["length"] = lengthCm;
        result["width"] = widthCm;
        result["depth"] = depthCm;
        return result;
    }

    private static bool Succeeded(Dictionary<string, object?> result)
        => result.TryGetValue("success", out var value) && value is true;
}
