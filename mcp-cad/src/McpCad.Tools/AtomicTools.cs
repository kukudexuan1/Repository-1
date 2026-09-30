using McpCad.Core;
using McpCad.Core.Exceptions;
using ModelContextProtocol.Server;
using System.ComponentModel;
using System.Text.Json;

namespace McpCad.Tools;

/// <summary>
/// Atomic MCP tools — one method per CAD operation.
/// Each method delegates to ICadProvider and catches COM exceptions,
/// returning standardized error dictionaries per the error contract (D7).
/// Tool method names use snake_case to match Python tool names (S5.1).
/// </summary>
[McpServerToolType]
public class AtomicTools(IMechanicalCadProvider provider)
{
    // ── Connection (3) ────────────────────────────────────────────────

    [McpServerTool, Description("Connect to a running Autodesk Inventor instance.")]
    public Dictionary<string, object?> inventor_connect()
        => Catch(provider.Connect);

    [McpServerTool, Description("Disconnect from Inventor without closing the application.")]
    public Dictionary<string, object?> inventor_disconnect()
        => Catch(provider.Disconnect);

    [McpServerTool, Description("Check Inventor connection health and document state.")]
    public Dictionary<string, object?> inventor_health()
        => Catch(provider.Health);

    // ── Documents (6) ────────────────────────────────────────────────

    [McpServerTool, Description("Open an existing Inventor document.")]
    public Dictionary<string, object?> doc_open(string path)
        => Catch(() => provider.DocOpen(path));

    [McpServerTool, Description("Create a new part document.")]
    public Dictionary<string, object?> doc_new_part(string template = "")
        => Catch(() => provider.DocNewPart(template));

    [McpServerTool, Description("Create a new assembly document.")]
    public Dictionary<string, object?> doc_new_assembly(string template = "")
        => Catch(() => provider.DocNewAssembly(template));

    [McpServerTool, Description("Save the active document.")]
    public Dictionary<string, object?> doc_save()
        => Catch(provider.DocSave);

    [McpServerTool, Description("Save the active document to a new path.")]
    public Dictionary<string, object?> doc_save_as(string path)
        => Catch(() => provider.DocSaveAs(path));

    [McpServerTool, Description("Close the active document.")]
    public Dictionary<string, object?> doc_close(bool save = true)
        => Catch(() => provider.DocClose(save));

    // ── Sketch (18) ────────────────────────────────────────────────────

    [McpServerTool, Description("Create a new sketch on the specified work plane.")]
    public Dictionary<string, object?> sketch_create(string plane = "XY")
        => Catch(() => provider.SketchCreate(plane));

    [McpServerTool, Description("Draw a line segment. Use connect=True to chain lines into a profile.")]
    public Dictionary<string, object?> sketch_line(
        double x1, double y1, double x2, double y2,
        string? tag = null, bool connect = false)
        => Catch(() => provider.SketchLine(x1, y1, x2, y2, tag, connect));

    [McpServerTool, Description("Draw a circle. Use tag=\"name\" to tag for @name resolution.")]
    public Dictionary<string, object?> sketch_circle(double cx, double cy, double radius, string? tag = null)
        => Catch(() => provider.SketchCircle(cx, cy, radius, tag));

    [McpServerTool, Description("Draw an arc in the active sketch.")]
    public Dictionary<string, object?> sketch_arc(
        double cx, double cy, double radius, double start_angle, double end_angle)
        => Catch(() => provider.SketchArc(cx, cy, radius, start_angle, end_angle));

    [McpServerTool, Description("Draw a rectangle in the active sketch.")]
    public Dictionary<string, object?> sketch_rectangle(double x1, double y1, double x2, double y2)
        => Catch(() => provider.SketchRectangle(x1, y1, x2, y2));

    [McpServerTool, Description("Add a dimension constraint. Modes: linear, radius, diameter, angle.")]
    public Dictionary<string, object?> sketch_dimension(
        string mode, string entity1, string entity2 = "",
        double? value = null, string orientation = "aligned",
        double? position_x = null, double? position_y = null)
        => Catch(() => provider.SketchDimension(mode, entity1, entity2, value, orientation, position_x, position_y));

    [McpServerTool, Description("Draw a point in the active sketch.")]
    public Dictionary<string, object?> sketch_point(double x, double y)
        => Catch(() => provider.SketchPoint(x, y));

    [McpServerTool, Description("Draw a spline through fit points.")]
    public Dictionary<string, object?> sketch_spline(string points, string fit_method = "sweet")
        => Catch(() => provider.SketchSpline(points, fit_method));

    [McpServerTool, Description("Draw an ellipse in the active sketch.")]
    public Dictionary<string, object?> sketch_ellipse(
        double cx, double cy, double major_radius, double minor_radius, double major_axis_angle = 0.0)
        => Catch(() => provider.SketchEllipse(cx, cy, major_radius, minor_radius, major_axis_angle));

    [McpServerTool, Description("Create a circular pattern of sketch entities.")]
    public Dictionary<string, object?> sketch_circular_pattern(
        string entities, string axis, int count,
        double angle = 360.0, bool fitted = true, bool symmetric = false)
        => Catch(() => provider.SketchCircularPattern(entities, axis, count, angle, fitted, symmetric));

    [McpServerTool, Description("Create a rectangular pattern of sketch entities.")]
    public Dictionary<string, object?> sketch_rectangular_pattern(
        string entities, string x_axis, int x_count, double x_spacing,
        string y_axis = "", int y_count = 1, double y_spacing = 0.0)
        => Catch(() => provider.SketchRectangularPattern(entities, x_axis, x_count, x_spacing, y_axis, y_count, y_spacing));

    [McpServerTool, Description("Offset sketch entities through a point (cm).")]
    public Dictionary<string, object?> sketch_offset(
        string entities, double offset_x, double offset_y, bool include_connected = false)
        => Catch(() => provider.SketchOffset(entities, offset_x, offset_y, include_connected));

    [McpServerTool, Description("Move sketch entities by a vector (cm).")]
    public Dictionary<string, object?> sketch_move(string entities, double dx, double dy, bool copy = false)
        => Catch(() => provider.SketchMove(entities, dx, dy, copy));

    [McpServerTool, Description("Rotate sketch entities around a center point (degrees).")]
    public Dictionary<string, object?> sketch_rotate(string entities, double cx, double cy, double angle, bool copy = false)
        => Catch(() => provider.SketchRotate(entities, cx, cy, angle, copy));

    [McpServerTool, Description("Delete the active sketch (must not be used by a feature).")]
    public Dictionary<string, object?> sketch_delete()
        => Catch(provider.SketchDelete);

    [McpServerTool, Description("Add a geometric constraint between sketch entities.")]
    public Dictionary<string, object?> sketch_constraint(
        string mode, string entity1, string entity2 = "",
        string sym_line = "", string axis = "major")
        => Catch(() => provider.SketchConstraint(mode, entity1, entity2, sym_line, axis));

    [McpServerTool, Description("Trim a sketch entity to its intersection with another.")]
    public Dictionary<string, object?> sketch_trim(string entity, string cutting_entity, string side = "end")
        => Catch(() => provider.SketchTrim(entity, cutting_entity, side));

    [McpServerTool, Description("Scale sketch entities around a center point.")]
    public Dictionary<string, object?> sketch_scale(string entities, double cx, double cy, double factor)
        => Catch(() => provider.SketchScale(entities, cx, cy, factor));

    [McpServerTool, Description("Mirror sketch entities across a mirror line.")]
    public Dictionary<string, object?> sketch_mirror(string entities, string mirror_entity)
        => Catch(() => provider.SketchMirror(entities, mirror_entity));

    [McpServerTool, Description("List all closed profiles in the active sketch with area info. Use before extrude/revolve to pick the correct profile index.")]
    public Dictionary<string, object?> sketch_profiles()
        => Catch(provider.SketchProfiles);

    // ── Features (5) ──────────────────────────────────────────────────

    [McpServerTool, Description("Extrude a sketch profile to create a 3D feature. Use profile: \"1\" for single region, or \"2,4\" for multiple regions (comma-separated indices). Run sketch_profiles() first to see available profiles and their centroids.")]
    public Dictionary<string, object?> extrude(
        string profile, double distance, string direction = "positive",
        double taper = 0.0, string operation = "new_body")
        => Catch(() => provider.Extrude(profile, distance, direction, taper, operation));

    [McpServerTool, Description("Revolve a profile around an axis (360° torus or partial sweep).")]
    public Dictionary<string, object?> revolve(
        string profile, string axis, double angle = 360.0,
        string direction = "positive", string operation = "join")
        => Catch(() => provider.Revolve(profile, axis, angle, direction, operation));

    [McpServerTool, Description("Sweep a profile along a path of connected sketch entities. Create profile sketch first, then path sketch. Use profile_sketch=\"last\" when profile is in the previous sketch.")]
    public Dictionary<string, object?> sweep(
        string profile, string path,
        string sweep_type = "path", string operation = "new_body",
        double taper = 0, string path_sketch = "", string profile_sketch = "")
        => Catch(() => provider.Sweep(profile, path, sweep_type, operation, taper, path_sketch, profile_sketch));

    [McpServerTool, Description("Apply a fillet to the specified edges.")]
    public Dictionary<string, object?> fillet(string edges, double radius, string mode = "constant")
        => Catch(() => provider.Fillet(edges, radius, mode));

    [McpServerTool, Description("Apply a chamfer to the specified edges.")]
    public Dictionary<string, object?> chamfer(string edges, double distance, string mode = "equal_distance")
        => Catch(() => provider.Chamfer(edges, distance, mode));

    [McpServerTool, Description("Create a circular pattern of a feature around an axis.")]
    public Dictionary<string, object?> circular_pattern(
        string profile, string axis, int count,
        double angle = 360.0, bool fit_within_angle = true, bool natural_direction = true)
        => Catch(() => provider.CircularPattern(profile, axis, count, angle, fit_within_angle, natural_direction));

    [McpServerTool, Description("Mirror a feature across a work plane.")]
    public Dictionary<string, object?> mirror_feature(string profile, string mirror_plane)
        => Catch(() => provider.MirrorFeature(profile, mirror_plane));

    [McpServerTool, Description("Create a rectangular pattern of a feature along one or two axes.")]
    public Dictionary<string, object?> rectangular_pattern(
        string profile, string x_axis, int x_count, double x_spacing,
        string y_axis = "", int y_count = 1, double y_spacing = 0.0)
        => Catch(() => provider.RectangularPattern(profile, x_axis, x_count, x_spacing, y_axis, y_count, y_spacing));

    [McpServerTool, Description("Create a loft feature between two or more profiles.")]
    public Dictionary<string, object?> loft(string profiles, string operation = "new_body")
        => Catch(() => provider.Loft(profiles, operation));

    [McpServerTool, Description("Create a coil (spring) feature.")]
    public Dictionary<string, object?> coil(string profile, string axis, double pitch, double revolutions, string operation = "new_body")
        => Catch(() => provider.Coil(profile, axis, pitch, revolutions, operation));

    [McpServerTool, Description("Create a rib (reinforcement) feature.")]
    public Dictionary<string, object?> rib(string profile, double thickness, string direction = "normal", string operation = "new_body")
        => Catch(() => provider.Rib(profile, thickness, direction, operation));

    [McpServerTool, Description("Create an emboss feature from a profile.")]
    public Dictionary<string, object?> emboss(string profile, double depth, string type = "emboss_from_face")
        => Catch(() => provider.Emboss(profile, depth, type));

    [McpServerTool, Description("Derive a part from an external file.")]
    public Dictionary<string, object?> derive(string source_path)
        => Catch(() => provider.Derive(source_path));

    [McpServerTool, Description("Create a hole feature at the specified position.")]
    public Dictionary<string, object?> hole(
        double x, double y, double diameter, double depth,
        string type = "drilled", string operation = "join")
        => Catch(() => provider.Hole(x, y, diameter, depth, type, operation));

    [McpServerTool, Description("Create a thread feature on a cylindrical face.")]
    public Dictionary<string, object?> thread(string face, string specification, string direction = "right")
        => Catch(() => provider.Thread(face, specification, direction));

    [McpServerTool, Description("List all edges of the active body with geometry info for selection.")]
    public Dictionary<string, object?> inspect_edges()
        => Catch(provider.InspectEdges);

    // ── Modify Features (5) ────────────────────────────────────────────

    [McpServerTool, Description("Create a shell feature by removing selected faces and applying uniform thickness to the remaining faces.")]
    public Dictionary<string, object?> shell(
        string faces, double thickness, string direction = "inside", string operation = "new_body")
        => Catch(() => provider.Shell(faces, thickness, direction, operation));

    [McpServerTool, Description("Create a solid feature by offsetting selected faces by a thickness value. Requires a surface body as input.")]
    public Dictionary<string, object?> thicken(
        string faces, double thickness, string direction = "positive", string operation = "new_body")
        => Catch(() => provider.Thicken(faces, thickness, direction, operation));

    [McpServerTool, Description("Combine bodies via boolean operation (join, cut, intersect). Base body and tool bodies are 1-based body indices (tool_bodies may be comma-separated).")]
    public Dictionary<string, object?> combine(
        string base_body, string tool_bodies, string operation = "join", bool keep_tool_bodies = false)
        => Catch(() => provider.Combine(base_body, tool_bodies, operation, keep_tool_bodies));

    [McpServerTool, Description("Split a body using a work plane as the splitting tool.")]
    public Dictionary<string, object?> split(
        string split_tool, string remove_side = "positive", string target_body = "")
        => Catch(() => provider.Split(split_tool, remove_side, target_body));

    [McpServerTool, Description("Apply a draft angle to the specified faces. Pull direction: x, y, or z. Fixed entity: eN for a specific edge, or empty to draft all edges of the selected faces.")]
    public Dictionary<string, object?> draft(
        string faces, double angle, string mode = "fixed_edge",
        string pull_direction = "z", string fixed_entity = "")
        => Catch(() => provider.Draft(faces, angle, mode, pull_direction, fixed_entity));

    // ── Parameters (4) ────────────────────────────────────────────────

    [McpServerTool, Description("List model parameters, optionally filtered by name pattern.")]
    public Dictionary<string, object?> param_list(string? filter_pattern = null)
        => Catch(() => provider.ParamList(filter_pattern));

    [McpServerTool, Description("Get a specific model parameter by name.")]
    public Dictionary<string, object?> param_get(string name)
        => Catch(() => provider.ParamGet(name));

    [McpServerTool, Description("Set a model parameter value by name.")]
    public Dictionary<string, object?> param_set(string name, double value)
        => Catch(() => provider.ParamSet(name, value));

    [McpServerTool, Description("Set a model parameter using an expression (e.g. 'd0 * 2').")]
    public Dictionary<string, object?> param_set_expression(string name, string expression)
        => Catch(() => provider.ParamSetExpression(name, expression));

    // ── Properties (5) ────────────────────────────────────────────────

    [McpServerTool, Description("Get an iProperty value by name.")]
    public Dictionary<string, object?> iproperty_get(string name, string property_set = "Summary")
        => Catch(() => provider.IPropertyGet(name, property_set));

    [McpServerTool, Description("Set an iProperty value by name.")]
    public Dictionary<string, object?> iproperty_set(string name, string? value, string property_set = "Summary")
        => Catch(() => provider.IPropertySet(name, value, property_set));

    [McpServerTool, Description("Get all Summary iProperties.")]
    public Dictionary<string, object?> iproperty_summary()
        => Catch(provider.IPropertySummary);

    [McpServerTool, Description("Get a custom iProperty by name.")]
    public Dictionary<string, object?> iproperty_custom_get(string name)
        => Catch(() => provider.IPropertyCustomGet(name));

    [McpServerTool, Description("Set a custom iProperty. Creates it if it doesn't exist.")]
    public Dictionary<string, object?> iproperty_custom_set(string name, string? value)
        => Catch(() => provider.IPropertyCustomSet(name, value));

    // ── Export (4) ─────────────────────────────────────────────────────

    [McpServerTool, Description("Export the active document to STEP format.")]
    public Dictionary<string, object?> export_step(string path, Dictionary<string, object?>? options = null)
        => Catch(() => provider.ExportStep(path, options));

    [McpServerTool, Description("Export the active document to STL format.")]
    public Dictionary<string, object?> export_stl(string path, Dictionary<string, object?>? options = null)
        => Catch(() => provider.ExportStl(path, options));

    [McpServerTool, Description("Export the active document to PDF format.")]
    public Dictionary<string, object?> export_pdf(string path, Dictionary<string, object?>? options = null)
        => Catch(() => provider.ExportPdf(path, options));

    [McpServerTool, Description("Export the active document's sketch or flat pattern to DXF.")]
    public Dictionary<string, object?> export_dxf(string path, Dictionary<string, object?>? options = null)
        => Catch(() => provider.ExportDxf(path, options));

    // ── Work Features (3) ──────────────────────────────────────────────

    [McpServerTool, Description("Create a work plane in the active part document. Supported definitions: default(1-3), offset_from_plane, through_three_points, normal_to_curve.")]
    public Dictionary<string, object?> work_plane(
        string definition, string reference1 = "", string reference2 = "", double? offset = null)
        => Catch(() => provider.WorkPlane(definition, reference1, reference2, offset ?? 0.0));

    [McpServerTool, Description("Create a work axis in the active part document. Supported definitions: default(1-3), through_two_points, normal_to_plane, along_edge.")]
    public Dictionary<string, object?> work_axis(
        string definition, string reference1 = "", string reference2 = "")
        => Catch(() => provider.WorkAxis(definition, reference1, reference2));

    [McpServerTool, Description("Create a work point in the active part document. Supported definitions: default, at_coordinates, on_curve, intersection.")]
    public Dictionary<string, object?> work_point(
        string definition, string reference1 = "", string reference2 = "", string reference3 = "")
        => Catch(() => provider.WorkPoint(definition, reference1, reference2, reference3));

    // ── Assembly (16) ──────────────────────────────────────────────────

    [McpServerTool, Description("List all placed components (occurrences) in the active assembly with their names, grounded state, and source paths.")]
    public Dictionary<string, object?> asm_list_components()
        => Catch(provider.AsmListComponents);

    [McpServerTool, Description("List all assembly constraints with their type, offset, and suppressed state.")]
    public Dictionary<string, object?> asm_list_constraints()
        => Catch(provider.AsmListConstraints);

    [McpServerTool, Description("Place a component into the assembly at an optional x,y,z position (cm). Path must be an absolute file path to an .ipt or .iam.")]
    public Dictionary<string, object?> asm_place_component(
        string path, double x = 0.0, double y = 0.0, double z = 0.0)
        => Catch(() => provider.AsmPlaceComponent(path, x, y, z));

    [McpServerTool, Description("Ground (fix in place) a component by name or 1-based occurrence index.")]
    public Dictionary<string, object?> asm_ground_component(string occurrence)
        => Catch(() => provider.AsmGroundComponent(occurrence));

    [McpServerTool, Description("Replace an occurrence with a different part file, retaining compatible constraints.")]
    public Dictionary<string, object?> asm_replace_component(string occurrence, string new_path)
        => Catch(() => provider.AsmReplaceComponent(occurrence, new_path));

    [McpServerTool, Description("Delete an assembly constraint by name or 1-based index.")]
    public Dictionary<string, object?> asm_delete_constraint(string constraint)
        => Catch(() => provider.AsmDeleteConstraint(constraint));

    [McpServerTool, Description("Create a mate constraint between two entities. Entity format: 'OccName/N' for face, 'OccName/eN' for edge, '@PlaneName' for work plane.")]
    public Dictionary<string, object?> asm_constraint_mate(
        string entity_one, string entity_two, double offset = 0.0)
        => Catch(() => provider.AsmConstraintMate(entity_one, entity_two, offset));

    [McpServerTool, Description("Create a flush constraint between two planar entities. Entity format: 'OccName/N' for face, '@PlaneName' for work plane.")]
    public Dictionary<string, object?> asm_constraint_flush(
        string entity_one, string entity_two, double offset = 0.0)
        => Catch(() => provider.AsmConstraintFlush(entity_one, entity_two, offset));

    [McpServerTool, Description("Create an angle constraint between two entities. Solution: directed, undirected, reference_vector.")]
    public Dictionary<string, object?> asm_constraint_angle(
        string entity_one, string entity_two, double angle, string solution = "directed")
        => Catch(() => provider.AsmConstraintAngle(entity_one, entity_two, angle, solution));

    [McpServerTool, Description("Create an insert constraint (concentric + planar) between two circular entities.")]
    public Dictionary<string, object?> asm_constraint_insert(
        string entity_one, string entity_two, double offset = 0.0)
        => Catch(() => provider.AsmConstraintInsert(entity_one, entity_two, offset));

    [McpServerTool, Description("Create a tangent constraint between two entities.")]
    public Dictionary<string, object?> asm_constraint_tangent(
        string entity_one, string entity_two, double offset = 0.0)
        => Catch(() => provider.AsmConstraintTangent(entity_one, entity_two, offset));

    [McpServerTool, Description("Create a circular pattern of an assembly occurrence around an axis (X, Y, Z, work axis index, or eN for edge).")]
    public Dictionary<string, object?> asm_pattern_circular(
        string occurrence, string axis, int count, double angle = 360.0)
        => Catch(() => provider.AsmCircularPattern(occurrence, axis, count, angle));

    [McpServerTool, Description("Create a rectangular pattern of an assembly occurrence along one or two axes.")]
    public Dictionary<string, object?> asm_pattern_rectangular(
        string occurrence, string x_axis, int x_count, double x_spacing,
        string? y_axis = null, int y_count = 1, double y_spacing = 0.0)
        => Catch(() => provider.AsmRectangularPattern(occurrence, x_axis, x_count, x_spacing, y_axis, y_count, y_spacing));

    [McpServerTool, Description("Create an extrude cut across multiple components at the assembly level. Requires an existing sketch.")]
    public Dictionary<string, object?> asm_extrude_cut(
        string profile, double distance, string direction = "positive")
        => Catch(() => provider.AsmExtrudeCut(profile, distance, direction));

    [McpServerTool, Description("Create a hole feature at the assembly level. Requires an existing sketch with a point.")]
    public Dictionary<string, object?> asm_hole(
        double x, double y, double diameter, double depth, string type = "drilled")
        => Catch(() => provider.AsmHole(x, y, diameter, depth, type));

    [McpServerTool, Description("Get the bill of materials (BOM) for the active assembly with part numbers, quantities, and descriptions.")]
    public Dictionary<string, object?> asm_bom()
        => Catch(provider.AsmBom);

    // ── Inspection & Visual Feedback (for LLM self-verification / retroalimentación de imágenes) ─
    // These tools implement the two approaches:
    // 1. Multimodal: CaptureViewportImage returns a Base64 screenshot of the viewport so a vision model can visually verify the result.
    // 2. Data-driven: GetFeatureTree + GetBoundingBox let the LLM inspect the exact operation tree and geometry via Inventor's API (no image needed).

    [McpServerTool, Description("Capture a screenshot of the active 3D viewport (or CAD window). Returns the image as Base64 (plus a 'content' array with type:'image' for clients that support native MCP image blocks). The LLM with vision can use this to visually verify the result of modeling operations (geometry correctness, collisions, etc.). This enables the multimodal feedback path.")]
    public Dictionary<string, object?> capture_viewport_image(string view = "Iso", int width = 1024, int height = 768, string format = "png")
    {
        var dict = Catch(() => provider.CaptureViewportImage(view, width, height, format));

        if (dict.TryGetValue("image_base64", out var b64) && b64 is string base64 && !string.IsNullOrEmpty(base64))
        {
            string mime = dict.TryGetValue("mime_type", out var m) && m is string ms ? ms : "image/png";

            // Also provide the native MCP content structure so clients that support it (as described) can forward the image directly to the vision model.
            dict["content"] = new[]
            {
                new Dictionary<string, object?>
                {
                    ["type"] = "image",
                    ["data"] = base64,
                    ["mimeType"] = mime
                }
            };
        }

        return dict;
    }

    [McpServerTool, Description("Return the structured feature/operation tree of the active document (parts: features; assemblies: occurrences + constraints). Enables the 'Árbol de Operaciones' / data inspection approach so the LLM can verify structure, order, and dependencies directly from the Inventor model without relying on vision.")]
    public Dictionary<string, object?> get_feature_tree()
        => Catch(provider.GetFeatureTree);

    [McpServerTool, Description("Return bounding box (min/max, size, center) for the model, a body, or a specific tagged entity. Provides direct vector/geometry data for precise verification (intersections, extents) as the data-driven complement to image feedback.")]
    public Dictionary<string, object?> get_bounding_box(string target = "")
        => Catch(() => provider.GetBoundingBox(target));

    [McpServerTool, Description("Return exact solid body count.")]
    public Dictionary<string, object?> get_body_count() => Catch(provider.GetBodyCount);

    [McpServerTool, Description("Inspect a feature by stable name or index.")]
    public Dictionary<string, object?> inspect_feature(string target) => Catch(() => provider.InspectFeature(target));

    [McpServerTool, Description("Measure section diameter normal to an axis at a position in cm.")]
    public Dictionary<string, object?> measure_section(string axis, double position_cm)
        => Catch(() => provider.MeasureSection(axis, position_cm));

    [McpServerTool, Description(
        "Return a structured JSON description of the active part geometry, mirroring SimpleCADAPI inspect_step_rsummary. " +
        "Includes per-body stats (volume, surface_area, face_count, edge_count, vertex_count, bounding_box), " +
        "surface_type_statistics (PLANE/CYLINDER/CONE/SPHERE/TORUS/BSPLINE counts), " +
        "curve_type_statistics (LINE/CIRCLE/ELLIPSE/BSPLINE counts), " +
        "and optionally per-face detail (entity_id, surface_type, area, centroid, normal_at_center, geometry parameters, adjacency). " +
        "Use include_faces=true (default) for face-level topology. Use include_edges=true to also include edge geometry. " +
        "max_faces caps face detail per body (default 64). " +
        "entity_id format: 'face:N' or 'edge:N' (zero-based). length_unit: cm (Inventor internal). " +
        "Call this after any modeling operation to give the LLM a data-driven understanding of the 3D structure without relying on vision.")]
    public Dictionary<string, object?> get_model_json(
        bool include_faces = true,
        bool include_edges = false,
        int  max_faces     = 64)
        => Catch(() => provider.GetModelJson(include_faces, include_edges, max_faces));

    [McpServerTool, Description(
        "Return full geometry detail for one face or edge identified by entity_id. " +
        "entity_id format: 'face:N' or 'edge:N' (zero-based index within the body). " +
        "body_index selects the body in multi-body parts (0-based, default 0). " +
        "Face response includes: surface_type, area, centroid, normal_at_center, normal_samples (3x3 grid), " +
        "uv_range, geometry parameters (radius/axis/normal/origin depending on type), bounding_box, adjacency (edge ids + neighboring face ids). " +
        "Edge response includes: curve_type, length, start/end vertices, geometry parameters (radius/center/axis for circles, direction for lines), adjacency (face ids). " +
        "Mirrors SimpleCADAPI inspect_step_entity_rdescriptor. " +
        "Use this to verify a specific face or edge after a modeling operation, or to resolve entity_ids for fillet/chamfer/shell/thread targets.")]
    public Dictionary<string, object?> get_entity_detail(string entity_id, int body_index = 0)
        => Catch(() => provider.GetEntityDetail(entity_id, body_index));

    [McpServerTool, Description("Create one deterministic 360-degree revolved body from JSON [axis,radius] profile points.")]
    public Dictionary<string, object?> create_revolved_profile(string name, string main_axis, string profile_points_json)
        => Catch(() => provider.CreateRevolvedProfile(name, main_axis, profile_points_json));

    [McpServerTool, Description("Cut a deterministic axial keyway on the specified shaft segment.")]
    public Dictionary<string, object?> cut_keyway(string name, string main_axis, string target_segment,
        double segment_start_cm, double segment_end_cm, double segment_diameter_cm,
        double axis_start_cm, double axis_end_cm, string radial_direction,
        double length_cm, double width_cm, double depth_cm)
        => Catch(() => provider.CutKeyway(name, main_axis, target_segment, segment_start_cm, segment_end_cm,
            segment_diameter_cm, axis_start_cm, axis_end_cm, radial_direction, length_cm, width_cm, depth_cm));

    [McpServerTool, Description("Run structural checks available in the CAD server and return evidence.")]
    public Dictionary<string, object?> verify_model_geometry()
    {
        var bodies = Catch(provider.GetBodyCount);
        var bbox = Catch(() => provider.GetBoundingBox("model"));
        bool ok = bodies.TryGetValue("body_count", out var count) && Convert.ToInt32(count) == 1
            && bbox.TryGetValue("success", out var success) && success is true;
        return new Dictionary<string, object?> { ["success"] = ok, ["body_count"] = bodies, ["bounding_box"] = bbox };
    }

    // ── Error catching helper (D7: tool-layer catches COM exceptions) ─

    private static Dictionary<string, object?> Catch(Func<Dictionary<string, object?>> action)
    {
        try
        {
            return action();
        }
        catch (InventorConnectionException ex)
        {
            return ToolHelpers.Error(ex.Message);
        }
        catch (InventorComException ex)
        {
            return ToolHelpers.Error(ex.Message);
        }
        catch (Exception ex)
        {
            return ToolHelpers.Error($"Unexpected error: {ex.Message}");
        }
    }
}