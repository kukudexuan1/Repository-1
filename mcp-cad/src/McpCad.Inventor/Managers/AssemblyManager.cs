using McpCad.Core.Exceptions;
using McpCad.Core.Models;
using McpCad.Inventor.Helpers;
using InvApp = Inventor.Application;

namespace McpCad.Inventor.Managers;

/// <summary>
/// Manages assembly-level operations: component placement, constraints,
/// patterns, assembly features, and BOM.
/// Uses InventorDriver for COM connection and delegates entity resolution
/// to dedicated helpers.
/// </summary>
public class AssemblyManager
{
    private readonly InventorDriver _driver;

    // Constraint offset/increment direction (MateConstraintDirectionEnum)
    // kAligned = 16901, kOpposed = 16902
    private const int MateOpposed = 16902;  // default: opposed

    public AssemblyManager(InventorDriver driver) => _driver = driver;

    // ── Internal guards ───────────────────────────────────────────────

    private InvApp App => _driver.InventorApp;

    private dynamic ActiveDocument()
    {
        var doc = _driver.ActiveDocument
            ?? throw new InventorComException("No active document. Open or create a document first.");
        return doc;
    }

    private dynamic AssemblyDefinition()
    {
        var compDef = _driver.ComponentDefinition
            ?? throw new InventorComException("No component definition available.");

        // Verify it's an assembly
        try
        {
            var doc = ActiveDocument();
            int docType = doc.DocumentType;
            // kAssemblyDocumentObject = 12291
            if (docType != 12291)
                throw new InventorComException("Active document is not an assembly. Open or create an assembly first.");
        }
        catch (InventorComException) { throw; }
        catch { /* fall through if DocumentType check fails */ }

        return ComDispatchHelper.WrapDispatch(compDef);
    }

    // ── Component listing ────────────────────────────────────────────

    /// <summary>
    /// List all occurrences (placed components) in the assembly.
    /// </summary>
    public Dictionary<string, object?> AsmListComponents()
    {
        try
        {
            var compDef = AssemblyDefinition();
            dynamic occurrences = compDef.Occurrences;

            var items = new List<Dictionary<string, object?>>();
            for (int i = 1; i <= occurrences.Count; i++)
            {
                dynamic occ = occurrences.Item(i);
                var info = new Dictionary<string, object?>
                {
                    ["index"] = i,
                    ["name"] = occ.Name,
                };
                try { info["grounded"] = occ.Grounded; } catch { }
                try { info["visible"] = occ.Visible; } catch { }
                try
                {
                    dynamic doc = occ.Definition?.Document;
                    if (doc != null)
                        info["source_path"] = doc.FullFileName as string;
                }
                catch { }
                items.Add(info);
            }

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["count"] = occurrences.Count,
                ["occurrences"] = items,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to list components: {ex.Message}", ex); }
    }

    // ── Constraint listing ───────────────────────────────────────────

    /// <summary>
    /// List all constraints in the assembly.
    /// </summary>
    public Dictionary<string, object?> AsmListConstraints()
    {
        try
        {
            var compDef = AssemblyDefinition();
            dynamic constraints = compDef.Constraints;

            var items = new List<Dictionary<string, object?>>();
            for (int i = 1; i <= constraints.Count; i++)
            {
                dynamic c = constraints.Item(i);
                var info = new Dictionary<string, object?>
                {
                    ["index"] = i,
                    ["name"] = c.Name,
                };
                try { info["type"] = c.Type?.ToString(); } catch { }
                try { info["suppressed"] = c.Suppressed; } catch { }
                try
                {
                    // Try to get entity names
                    info["entity_one"] = c.EntityOne?.Name as string;
                    info["entity_two"] = c.EntityTwo?.Name as string;
                }
                catch { }
                try { info["offset"] = c.Offset?.Value; } catch { }
                items.Add(info);
            }

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["count"] = constraints.Count,
                ["constraints"] = items,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to list constraints: {ex.Message}", ex); }
    }

    // ── Place component ──────────────────────────────────────────────

    /// <summary>
    /// Place a component into the assembly at an optional position.
    /// </summary>
    public Dictionary<string, object?> AsmPlaceComponent(string path, double x = 0, double y = 0, double z = 0)
    {
        try
        {
            var compDef = AssemblyDefinition();
            dynamic occurrences = compDef.Occurrences;

            // Place with or without position matrix
            dynamic occ;
            if (x == 0 && y == 0 && z == 0)
            {
                // No position specified — place at origin with identity matrix
                dynamic tg = App.TransientGeometry;
                dynamic matrix = tg.CreateMatrix();
                occ = occurrences.Add(path, matrix);
            }
            else
            {
                dynamic tg = App.TransientGeometry;
                dynamic matrix = tg.CreateMatrix();
                // Set translation
                matrix.Cell[1, 4] = x;
                matrix.Cell[2, 4] = y;
                matrix.Cell[3, 4] = z;
                occ = occurrences.Add(path, matrix);
            }

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["component_name"] = occ.Name as string,
                ["source_path"] = path,
                ["position"] = new Dictionary<string, object?> { ["x"] = x, ["y"] = y, ["z"] = z },
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to place component '{path}': {ex.Message}", ex); }
    }

    // ── Ground component ─────────────────────────────────────────────

    /// <summary>
    /// Ground a component (fix it in place, removing all degrees of freedom).
    /// </summary>
    public Dictionary<string, object?> AsmGroundComponent(string occurrence)
    {
        try
        {
            var compDef = AssemblyDefinition();
            dynamic occ = ResolveOccurrence(compDef, occurrence);
            occ.Grounded = true;

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["occurrence"] = occ.Name as string,
                ["grounded"] = true,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to ground component: {ex.Message}", ex); }
    }

    // ── Replace component ────────────────────────────────────────────

    /// <summary>
    /// Replace an occurrence with a different part/assembly file.
    /// </summary>
    public Dictionary<string, object?> AsmReplaceComponent(string occurrence, string newPath)
    {
        try
        {
            var compDef = AssemblyDefinition();
            dynamic occ = ResolveOccurrence(compDef, occurrence);
            occ.Replace(newPath, true); // true = retain constraints where possible

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["occurrence"] = occ.Name as string,
                ["replaced_with"] = newPath,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to replace component: {ex.Message}", ex); }
    }

    // ── Delete constraint ────────────────────────────────────────────

    /// <summary>
    /// Delete a constraint by name or 1-based index.
    /// </summary>
    public Dictionary<string, object?> AsmDeleteConstraint(string constraint)
    {
        try
        {
            var compDef = AssemblyDefinition();
            dynamic constraints = compDef.Constraints;

            dynamic c;
            if (int.TryParse(constraint, out int idx) && idx >= 1 && idx <= constraints.Count)
            {
                c = constraints.Item(idx);
            }
            else
            {
                c = constraints.Item(constraint); // by name
            }

            string name = c.Name;
            c.Delete();

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["deleted"] = name,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to delete constraint: {ex.Message}", ex); }
    }

    // ── Mate constraint ──────────────────────────────────────────────

    /// <summary>
    /// Create a mate constraint between two entities.
    /// Entity format: "OccurrenceName/FaceIndex" (e.g. "Part1:1/3")
    /// or numeric face index for grounded body, or "@PlaneName".
    /// </summary>
    public Dictionary<string, object?> AsmConstraintMate(string entityOne, string entityTwo, double offset = 0)
    {
        try
        {
            var compDef = AssemblyDefinition();
            dynamic e1 = ResolveAssemblyEntity(compDef, entityOne);
            dynamic e2 = ResolveAssemblyEntity(compDef, entityTwo);

            dynamic constraints = compDef.Constraints;
            dynamic c = constraints.AddMateConstraint(
                e1, e2, offset,
                Type.Missing, Type.Missing,
                Type.Missing, Type.Missing);

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["constraint_type"] = "mate",
                ["constraint_name"] = c.Name as string,
                ["offset"] = offset,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to create mate constraint: {ex.Message}", ex); }
    }

    // ── Flush constraint ─────────────────────────────────────────────

    /// <summary>
    /// Create a flush constraint between two planar entities.
    /// </summary>
    public Dictionary<string, object?> AsmConstraintFlush(string entityOne, string entityTwo, double offset = 0)
    {
        try
        {
            var compDef = AssemblyDefinition();
            dynamic e1 = ResolveAssemblyEntity(compDef, entityOne);
            dynamic e2 = ResolveAssemblyEntity(compDef, entityTwo);

            dynamic constraints = compDef.Constraints;
            dynamic c = constraints.AddFlushConstraint(e1, e2, offset);

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["constraint_type"] = "flush",
                ["constraint_name"] = c.Name as string,
                ["offset"] = offset,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to create flush constraint: {ex.Message}", ex); }
    }

    // ── Angle constraint ─────────────────────────────────────────────

    /// <summary>
    /// Create an angle constraint between two entities.
    /// Solution: "directed" (kDirectedSolution=78593), "undirected" (78594),
    /// or "reference_vector" (78595).
    /// </summary>
    public Dictionary<string, object?> AsmConstraintAngle(string entityOne, string entityTwo, double angle, string solution = "directed")
    {
        try
        {
            var compDef = AssemblyDefinition();
            dynamic e1 = ResolveAssemblyEntity(compDef, entityOne);
            dynamic e2 = ResolveAssemblyEntity(compDef, entityTwo);

            int solEnum = solution.ToLowerInvariant() switch
            {
                "directed" => 78593,
                "undirected" => 78594,
                "reference_vector" => 78595,
                _ => 78593,
            };

            // Convert angle to radians for the API
            double angleRad = angle * Math.PI / 180.0;

            dynamic constraints = compDef.Constraints;
            dynamic c = constraints.AddAngleConstraint(
                e1, e2, angleRad, solEnum,
                Type.Missing, Type.Missing);

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["constraint_type"] = "angle",
                ["constraint_name"] = c.Name as string,
                ["angle"] = angle,
                ["solution"] = solution,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to create angle constraint: {ex.Message}", ex); }
    }

    // ── Insert constraint ────────────────────────────────────────────

    /// <summary>
    /// Create an insert constraint (concentric + planar) between two circular entities.
    /// </summary>
    public Dictionary<string, object?> AsmConstraintInsert(string entityOne, string entityTwo, double offset = 0)
    {
        try
        {
            var compDef = AssemblyDefinition();
            dynamic e1 = ResolveAssemblyEntity(compDef, entityOne);
            dynamic e2 = ResolveAssemblyEntity(compDef, entityTwo);

            dynamic constraints = compDef.Constraints;
            dynamic c = constraints.AddInsertConstraint(e1, e2, MateOpposed, offset);

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["constraint_type"] = "insert",
                ["constraint_name"] = c.Name as string,
                ["offset"] = offset,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to create insert constraint: {ex.Message}", ex); }
    }

    // ── Tangent constraint ───────────────────────────────────────────

    /// <summary>
    /// Create a tangent constraint between two entities.
    /// </summary>
    public Dictionary<string, object?> AsmConstraintTangent(string entityOne, string entityTwo, double offset = 0)
    {
        try
        {
            var compDef = AssemblyDefinition();
            dynamic e1 = ResolveAssemblyEntity(compDef, entityOne);
            dynamic e2 = ResolveAssemblyEntity(compDef, entityTwo);

            dynamic constraints = compDef.Constraints;
            dynamic c = constraints.AddTangentConstraint(
                e1, e2, MateOpposed, offset,
                Type.Missing, Type.Missing);

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["constraint_type"] = "tangent",
                ["constraint_name"] = c.Name as string,
                ["offset"] = offset,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to create tangent constraint: {ex.Message}", ex); }
    }

    // ── Circular pattern ─────────────────────────────────────────────

    /// <summary>
    /// Create a circular pattern of an assembly occurrence around an axis.
    /// </summary>
    public Dictionary<string, object?> AsmCircularPattern(string occurrence, string axis, int count, double angle = 360)
    {
        try
        {
            var compDef = AssemblyDefinition();
            dynamic occ = ResolveOccurrence(compDef, occurrence);
            dynamic patternAxis = ResolveAssemblyAxis(compDef, axis);

            // Create ObjectCollection with the occurrence
            dynamic oc = App.TransientObjects.CreateObjectCollection();
            oc.Add(occ);

            double angleRad = angle * Math.PI / 180.0;

            dynamic patterns = ComDispatchHelper.WrapDispatch(compDef.OccurrencePatterns);
            dynamic pattern = patterns.AddCircularPattern(oc, patternAxis, true, count, angleRad);

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["pattern_type"] = "circular",
                ["count"] = count,
                ["angle"] = angle,
                ["element_name"] = pattern.Name as string,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to create circular pattern: {ex.Message}", ex); }
    }

    // ── Rectangular pattern ──────────────────────────────────────────

    /// <summary>
    /// Create a rectangular pattern of an assembly occurrence.
    /// </summary>
    public Dictionary<string, object?> AsmRectangularPattern(
        string occurrence, string xAxis, int xCount, double xSpacing,
        string? yAxis = null, int yCount = 1, double ySpacing = 0)
    {
        try
        {
            var compDef = AssemblyDefinition();
            dynamic occ = ResolveOccurrence(compDef, occurrence);
            dynamic xDir = ResolveAssemblyAxis(compDef, xAxis);

            dynamic oc = App.TransientObjects.CreateObjectCollection();
            oc.Add(occ);

            dynamic patterns = ComDispatchHelper.WrapDispatch(compDef.OccurrencePatterns);
            dynamic pattern;
            if (!string.IsNullOrEmpty(yAxis) && yCount > 1)
            {
                dynamic yDir = ResolveAssemblyAxis(compDef, yAxis);
                pattern = patterns.AddRectangularPattern(
                    oc, xDir, true, xCount, xSpacing,
                    yDir, yCount, ySpacing, Type.Missing);
            }
            else
            {
                pattern = patterns.AddRectangularPattern(
                    oc, xDir, true, xCount, xSpacing,
                    Type.Missing, Type.Missing, Type.Missing, Type.Missing);
            }

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["pattern_type"] = "rectangular",
                ["x_count"] = xCount,
                ["x_spacing"] = xSpacing,
                ["y_count"] = yCount,
                ["y_spacing"] = ySpacing,
                ["element_name"] = pattern.Name as string,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to create rectangular pattern: {ex.Message}", ex); }
    }

    // ── Assembly extrude cut ─────────────────────────────────────────

    /// <summary>
    /// Create an extrude cut feature at the assembly level.
    /// </summary>
    public Dictionary<string, object?> AsmExtrudeCut(string profile, double distance, string direction = "positive")
    {
        try
        {
            var compDef = AssemblyDefinition();
            // Assembly features require existing sketch
            dynamic sketches = compDef.Sketches;
            if (sketches.Count == 0)
                throw new InventorComException("No sketch exists. Create a sketch on a face or work plane first.");

            dynamic sketch = sketches.Item(sketches.Count);

            // Resolve profile
            dynamic resolvedProfile = ResolveAssemblyProfile(compDef, profile, sketch);

            // Direction map (same as feature manager)
            var dirMap = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
            {
                ["positive"] = 20993,
                ["negative"] = 20994,
                ["symmetric"] = 20995,
            };
            if (!dirMap.TryGetValue(direction, out int dirEnum))
                return ErrorResult.Create($"Invalid direction '{direction}'. Use: positive, negative, symmetric.");

            // Use regular ExtrudeFeatures (AssemblyFeatures is not available in this API)
            dynamic extrudeFeatures = ComDispatchHelper.WrapDispatch(compDef.Features.ExtrudeFeatures);
            dynamic extrudeDef = extrudeFeatures.CreateExtrudeDefinition(resolvedProfile, 20482); // kCutOperation
            extrudeDef.SetDistanceExtent(distance, dirEnum);

            // Set which components are affected (all by default)
            dynamic affectedOccs = App.TransientObjects.CreateObjectCollection();
            dynamic occurrences = compDef.Occurrences;
            for (int i = 1; i <= occurrences.Count; i++)
                affectedOccs.Add(occurrences.Item(i));

            // Try setting AffectedOccurrences via late-bound (may not exist on older versions)
            try { extrudeDef.AffectedOccurrences = affectedOccs; }
            catch { /* pre-2020 Inventor — extrusion cuts all visible bodies by default */ }

            dynamic feature = extrudeFeatures.Add(extrudeDef);

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["feature_type"] = "assembly_extrude_cut",
                ["distance"] = distance,
                ["direction"] = direction,
                ["feature_name"] = feature.Name as string,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to create assembly extrude cut: {ex.Message}", ex); }
    }

    // ── Assembly hole ────────────────────────────────────────────────

    /// <summary>
    /// Create a hole feature at the assembly level.
    /// </summary>
    public Dictionary<string, object?> AsmHole(double x, double y, double diameter, double depth, string type = "drilled")
    {
        try
        {
            var compDef = AssemblyDefinition();

            // Need a sketch point for placement
            dynamic sketches = compDef.Sketches;
            if (sketches.Count == 0)
                throw new InventorComException("No sketch exists. Create a sketch first.");

            dynamic sketch = sketches.Item(sketches.Count);
            dynamic point = sketch.SketchPoints.Add(App.TransientGeometry.CreatePoint2d(x, y));

            dynamic pointCollection = App.TransientObjects.CreateObjectCollection();
            pointCollection.Add(point);

            // Use regular HoleFeatures — AssemblyFeatures may not be available
            dynamic holeFeatures = ComDispatchHelper.WrapDispatch(compDef.Features.HoleFeatures);
            dynamic placementDef = holeFeatures.CreateSketchPlacementDefinition(pointCollection);

            int dirEnum = 20993; // positive
            dynamic holeFeature = holeFeatures.AddDrilledByDistanceExtent(
                placementDef, diameter, depth, dirEnum,
                false, Type.Missing);

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["feature_type"] = "assembly_hole",
                ["x"] = x, ["y"] = y,
                ["diameter"] = diameter, ["depth"] = depth,
                ["hole_type"] = type,
                ["feature_name"] = holeFeature.Name as string,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to create assembly hole: {ex.Message}", ex); }
    }

    // ── BOM ──────────────────────────────────────────────────────────

    /// <summary>
    /// Get the bill of materials for the assembly.
    /// </summary>
    public Dictionary<string, object?> AsmBom()
    {
        try
        {
            var compDef = AssemblyDefinition();
            dynamic bom = compDef.BOM;
            // Ensure BOM is structured (not parts-only)
            bom.StructuredViewEnabled = true;
            dynamic bomView = bom.BOMViews.Item("Structured");

            var items = new List<Dictionary<string, object?>>();
            // BOM rows are 1-based
            for (int i = 1; i <= (int)bomView.BOMRows.Count; i++)
            {
                dynamic row = bomView.BOMRows.Item(i);
                var item = new Dictionary<string, object?>
                {
                    ["index"] = i,
                };
                try { item["part_number"] = row.ComponentDescription; } catch { }
                try { item["description"] = row.ComponentDescription; } catch { }
                try { item["quantity"] = row.ItemQuantity; } catch { }
                try { item["total_cost"] = row.TotalCost; } catch { }
                items.Add(item);
            }

            return new Dictionary<string, object?>
            {
                ["success"] = true,
                ["bom_structure"] = "structured",
                ["row_count"] = items.Count,
                ["items"] = items,
            };
        }
        catch (InventorConnectionException) { throw; }
        catch (InventorComException) { throw; }
        catch (Exception ex) { throw new InventorComException($"Failed to get BOM: {ex.Message}", ex); }
    }

    // ── Entity resolution helpers ────────────────────────────────────

    /// <summary>
    /// Resolve an assembly entity reference for constraint creation.
    /// Formats:
    ///   "OccName/FaceIndex"  -> occurrence face (e.g. "Part1:1/3")
    ///   "OccName/EdgeIndex"  -> occurrence edge (e.g. "Part1:1/2")
    ///   "OccName"            -> occurrence proxy (work point at origin)
    ///   "@PlaneName"         -> work plane by name
    ///   "wpn" or "n"         -> work plane by index
    ///   Number               -> occurrence by index, or face of first body
    /// </summary>
    private dynamic ResolveAssemblyEntity(dynamic compDef, string entityRef)
    {
        if (string.IsNullOrWhiteSpace(entityRef))
            throw new InventorComException("Entity reference cannot be empty.");

        // Work plane by @ tag — same convention as sketch
        if (entityRef.StartsWith("@"))
        {
            string planeName = entityRef[1..];
            try { return compDef.WorkPlanes.Item(planeName); }
            catch { throw new InventorComException($"Work plane '@{planeName}' not found."); }
        }

        // Work plane by "wp" prefix with numeric index
        if (entityRef.StartsWith("wp", StringComparison.OrdinalIgnoreCase) &&
            int.TryParse(entityRef[2..], out int wpIdx))
        {
            try { return compDef.WorkPlanes.Item(wpIdx); }
            catch { throw new InventorComException($"Work plane 'wp{wpIdx}' not found."); }
        }

        // Face/edge reference: "OccName/3" (face) or "OccName/e2" (edge)
        int slashPos = entityRef.LastIndexOf('/');
        if (slashPos > 0)
        {
            string occRef = entityRef[..slashPos];
            string subRef = entityRef[(slashPos + 1)..];

            dynamic occ = ResolveOccurrence(compDef, occRef);

            if (subRef.StartsWith("e", StringComparison.OrdinalIgnoreCase) &&
                int.TryParse(subRef[1..], out int edgeIdx))
            {
                // Edge reference — use raw edge directly
                try
                {
                    dynamic body = ResolveOccurrenceBody(occ);
                    return body.Edges.Item(edgeIdx);
                }
                catch { throw new InventorComException($"Edge 'e{edgeIdx}' not found on occurrence '{occRef}'."); }
            }

            if (int.TryParse(subRef, out int faceIdx))
            {
                // Face reference — use raw face directly (constraint API accepts them)
                try
                {
                    dynamic body = ResolveOccurrenceBody(occ);
                    return body.Faces.Item(faceIdx);
                }
                catch { throw new InventorComException($"Face '{faceIdx}' not found on occurrence '{occRef}'."); }
            }

            throw new InventorComException($"Invalid sub-reference '{subRef}'. Use N for face or eN for edge.");
        }

        // Numeric index: treat as occurrence index, face 1
        if (int.TryParse(entityRef, out int occIdx))
        {
            dynamic occ = ResolveOccurrence(compDef, entityRef);
            try
            {
                dynamic body = ResolveOccurrenceBody(occ);
                return body.Faces.Item(1);
            }
            catch { /* fall through: return the occurrence itself */ }
            return occ;
        }

        // Try as occurrence name
        try
        {
            dynamic occ = compDef.Occurrences.ItemByName(entityRef);
            return occ;
        }
        catch { }

        // Try as work plane name (without @)
        try { return compDef.WorkPlanes.Item(entityRef); }
        catch { }

        throw new InventorComException(
            $"Could not resolve entity '{entityRef}'. " +
            $"Use 'OccName/N' for face, 'OccName/eN' for edge, '@PlaneName' for work plane.");
    }

    /// <summary>
    /// Resolve an occurrence by name or 1-based index.
    /// </summary>
    private dynamic ResolveOccurrence(dynamic compDef, string occurrenceRef)
    {
        dynamic occurrences = compDef.Occurrences;

        if (int.TryParse(occurrenceRef, out int idx) && idx >= 1 && idx <= (int)occurrences.Count)
            return occurrences.Item(idx);

        try { return occurrences.ItemByName(occurrenceRef); }
        catch { }

        throw new InventorComException(
            $"Occurrence '{occurrenceRef}' not found. Use a 1-based index or occurrence name.");
    }

    /// <summary>
    /// Get the first surface body of an occurrence.
    /// In assembly context, SurfaceBodies lives on the occurrence directly (verified on Inventor 2026).
    /// </summary>
    private dynamic ResolveOccurrenceBody(dynamic occ)
    {
        try { return occ.SurfaceBodies.Item(1); }
        catch { }

        // Fallback: try through Definition
        try
        {
            dynamic def = occ.Definition;
            if (def != null)
            {
                dynamic doc = def.Document;
                if (doc != null)
                {
                    dynamic cd = ComDispatchHelper.WrapDispatch(doc.ComponentDefinition);
                    return cd.SurfaceBodies.Item(1);
                }
                return def.SurfaceBodies.Item(1);
            }
        }
        catch { }

        throw new InventorComException("Could not access surface bodies on occurrence.");
    }

    /// <summary>
    /// Resolve an axis reference for assembly patterns.
    /// Supports: "X", "Y", "Z", work axis index, edge index "eN".
    /// </summary>
    private dynamic ResolveAssemblyAxis(dynamic compDef, string axisRef)
    {
        if (string.IsNullOrWhiteSpace(axisRef))
            throw new InventorComException("Axis reference cannot be empty.");

        // Work axes: X=1, Y=2, Z=3
        switch (axisRef.ToUpperInvariant())
        {
            case "X": return compDef.WorkAxes.Item(1);
            case "Y": return compDef.WorkAxes.Item(2);
            case "Z": return compDef.WorkAxes.Item(3);
        }

        if (int.TryParse(axisRef, out int axisIdx))
        {
            try { return compDef.WorkAxes.Item(axisIdx); }
            catch { /* fall through */ }
        }

        // Edge with "e" prefix
        if (axisRef.StartsWith("e", StringComparison.OrdinalIgnoreCase) &&
            int.TryParse(axisRef[1..], out int edgeIdx))
        {
            try
            {
                dynamic body = compDef.SurfaceBodies.Item(1);
                return body.Edges.Item(edgeIdx);
            }
            catch { throw new InventorComException($"Edge '{axisRef}' not found."); }
        }

        throw new InventorComException($"Invalid axis '{axisRef}'. Use X, Y, Z, work axis index, or eN.");
    }

    /// <summary>
    /// Resolve a profile from the active assembly sketch.
    /// Delegates to ProfileResolver which handles both named and numeric references.
    /// </summary>
    private dynamic ResolveAssemblyProfile(dynamic compDef, string profileRef, dynamic sketch)
    {
        // Merge intersections first (same as FeatureManager)
        try { IntersectionMerger.MergeAll(sketch, App); }
        catch { /* Best-effort */ }

        // Use ProfileResolver for robust profile resolution
        try { return ProfileResolver.Resolve(sketch); }
        catch (Exception ex) { throw new InventorComException($"Failed to resolve profile: {ex.Message}", ex); }
    }
}
