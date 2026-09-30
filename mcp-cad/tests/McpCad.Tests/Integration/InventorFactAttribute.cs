// SPDX-License-Identifier: GPL-3.0-only
//
// Added by kukudexuan1 (2026) as part of the modified mcp-cad distribution.
// Based on mcp-cad (https://github.com/Andiveli/mcp-cad), licensed under GNU GPL v3.0.
// See the LICENSE file in the mcp-cad directory for the full license text.

namespace McpCad.Tests.Integration;

public sealed class InventorFactAttribute : FactAttribute
{
    public InventorFactAttribute()
    {
        if (!string.Equals(
                Environment.GetEnvironmentVariable("RUN_INVENTOR_INTEGRATION"),
                "1",
                StringComparison.Ordinal))
        {
            Skip = "Set RUN_INVENTOR_INTEGRATION=1 with Inventor running";
        }
    }
}
