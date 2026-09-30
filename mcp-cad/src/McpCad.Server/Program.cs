using McpCad.Core;
using McpCad.Inventor;
using McpCad.Tools;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

var builder = Host.CreateApplicationBuilder(args);

// Route all logging to stderr so it doesn't interfere with MCP stdio transport
builder.Logging.AddConsole(consoleLogOptions =>
{
    consoleLogOptions.LogToStandardErrorThreshold = LogLevel.Trace;
});

// Register the Inventor-backed provider as a singleton.
// The driver auto-connects on first use; startup connect is controlled by appsettings.
builder.Services.AddSingleton<InventorDriver>();
builder.Services.AddSingleton<IMechanicalCadProvider, InventorProvider>();
builder.Services.AddSingleton<ICadProvider>(sp => sp.GetRequiredService<IMechanicalCadProvider>());

// Register MCP server with stdio transport.
builder.Services
    .AddMcpServer()
    .WithStdioServerTransport()
    .WithTools<AtomicTools>()
    .WithTools<SkillTools>();

var app = builder.Build();

// Auto-connect to Inventor on startup if configured (non-blocking, safe to fail)
if (app.Services.GetRequiredService<IConfiguration>()
        .GetValue<bool>("Inventor:AutoConnect"))
{
    var driver = app.Services.GetRequiredService<InventorDriver>();
    driver.Connect();
}

await app.RunAsync();
