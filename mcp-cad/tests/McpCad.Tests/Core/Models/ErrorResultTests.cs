using McpCad.Core.Exceptions;
using McpCad.Core.Models;

namespace McpCad.Tests.Core.Models;

public class ErrorResultTests
{
    [Fact]
    public void Create_ReturnsSuccessFalse_WithMessage()
    {
        var result = ErrorResult.Create("Something failed");

        Assert.False((bool)result["success"]!);
        Assert.Equal("Something failed", result["error"]);
    }

    [Fact]
    public void Create_WithDetails_MergesExtraData()
    {
        var result = ErrorResult.Create("Not found",
            ("resource", (object?)"Sketch1"),
            ("code", (object?)404));

        Assert.False((bool)result["success"]!);
        Assert.Equal("Not found", result["error"]);
        Assert.Equal("Sketch1", result["resource"]);
        Assert.Equal(404, result["code"]);
    }

    [Fact]
    public void FromException_IncludesExceptionType()
    {
        var ex = new InventorComException("COM error occurred");
        var result = ErrorResult.FromException(ex);

        Assert.False((bool)result["success"]!);
        Assert.Equal("COM error occurred", result["error"]);
        Assert.Equal("InventorComException", result["exception_type"]);
    }

    [Fact]
    public void FromException_WithInventorConnectionException_IncludesType()
    {
        var ex = new InventorConnectionException("Inventor not running");
        var result = ErrorResult.FromException(ex);

        Assert.Equal("InventorConnectionException", result["exception_type"]);
    }
}

public class ExceptionsTests
{
    [Fact]
    public void InventorConnectionException_Message_PreservesMessage()
    {
        var ex = new InventorConnectionException("test message");

        Assert.Equal("test message", ex.Message);
    }

    [Fact]
    public void InventorConnectionException_InnerException_PreservesChain()
    {
        var inner = new InvalidOperationException("inner");
        var ex = new InventorConnectionException("outer", inner);

        Assert.Equal("outer", ex.Message);
        Assert.Same(inner, ex.InnerException);
    }

    [Fact]
    public void InventorComException_Message_PreservesMessage()
    {
        var ex = new InventorComException("COM failure");

        Assert.Equal("COM failure", ex.Message);
    }

    [Fact]
    public void InventorComException_WithHResult_IncludesHexCode()
    {
        var ex = new InventorComException("RPC failure", unchecked((int)0x80010108));

        Assert.Contains("0x80010108", ex.Message);
        Assert.Equal(unchecked((int)0x80010108), ex.ComHResult);
    }

    [Fact]
    public void InventorComException_WithInnerException_PreservesChain()
    {
        var inner = new Exception("inner");
        var ex = new InventorComException("outer", inner);

        Assert.Same(inner, ex.InnerException);
    }
}