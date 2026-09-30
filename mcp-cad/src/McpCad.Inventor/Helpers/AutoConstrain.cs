namespace McpCad.Inventor.Helpers;

/// <summary>
/// Adds coincident constraints between sequential SketchLines 
/// to close open profile loops, making them usable for feature operations.
/// </summary>
public static class AutoConstrain
{
    /// <summary>
    /// Add coincident constraints between sequential sketch lines to close loops.
    /// For each pair of consecutive lines, constrains the end point of line N
    /// to the start point of line N+1.
    /// </summary>
    /// <param name="sketch">The planar sketch to constrain.</param>
    /// <param name="sketchLineCount">Optional override for the number of lines to process. 
    /// If 0, processes all lines in the sketch.</param>
    public static void CloseSketch(dynamic sketch, int sketchLineCount = 0)
    {
        dynamic lines = sketch.SketchLines;
        int count = sketchLineCount > 0 ? sketchLineCount : lines.Count;

        if (count < 2)
            return;

        dynamic gc = sketch.GeometricConstraints;

        // Connect end of line N to start of line N+1
        for (int i = 1; i < count; i++)
        {
            try
            {
                dynamic prevLine = lines.Item(i);
                dynamic nextLine = lines.Item(i + 1);
                gc.AddCoincident(prevLine.EndSketchPoint, nextLine.StartSketchPoint);
            }
            catch
            {
                // Skip if already coincident or constraint can't be added
            }
        }

        // Close the loop: end of last line → start of first line
        try
        {
            dynamic lastLine = lines.Item(count);
            dynamic firstLine = lines.Item(1);
            gc.AddCoincident(lastLine.EndSketchPoint, firstLine.StartSketchPoint);
        }
        catch
        {
            // Skip if already coincident
        }
    }
}