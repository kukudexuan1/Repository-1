using McpCad.Inventor.Helpers;

namespace McpCad.Tests.Inventor;

public class TagStoreTests
{
    public TagStoreTests()
    {
        // Clear before each test since TagStore is static
        TagStore.Clear();
    }

    [Fact]
    public void SetTag_And_GetTag_ReturnsTag()
    {
        TagStore.SetTag(1, 3, "eje");

        var tag = TagStore.GetTag(1, 3);

        Assert.Equal("eje", tag);
    }

    [Fact]
    public void GetTag_ReturnsNull_WhenNotSet()
    {
        var tag = TagStore.GetTag(99, 1);

        Assert.Null(tag);
    }

    [Fact]
    public void SetTag_Overwrites_ExistingTag()
    {
        TagStore.SetTag(1, 3, "eje");
        TagStore.SetTag(1, 3, "axis");

        var tag = TagStore.GetTag(1, 3);

        Assert.Equal("axis", tag);
    }

    [Fact]
    public void Resolve_ReturnsEntityIndex_WhenTagExists()
    {
        TagStore.SetTag(1, 5, "profile");

        var result = TagStore.Resolve(1, "profile");

        Assert.Equal(5, result);
    }

    [Fact]
    public void Resolve_ReturnsNull_WhenTagNotFound()
    {
        var result = TagStore.Resolve(1, "nonexistent");

        Assert.Null(result);
    }

    [Fact]
    public void Resolve_IsScopedToSketchIndex()
    {
        TagStore.SetTag(1, 3, "eje");
        TagStore.SetTag(2, 7, "eje");

        var sketch1Result = TagStore.Resolve(1, "eje");
        var sketch2Result = TagStore.Resolve(2, "eje");

        Assert.Equal(3, sketch1Result);
        Assert.Equal(7, sketch2Result);
    }

    [Fact]
    public void Clear_RemovesAllTags()
    {
        TagStore.SetTag(1, 1, "a");
        TagStore.SetTag(1, 2, "b");
        TagStore.SetTag(2, 1, "c");

        TagStore.Clear();

        Assert.Null(TagStore.GetTag(1, 1));
        Assert.Null(TagStore.GetTag(1, 2));
        Assert.Null(TagStore.GetTag(2, 1));
    }

    [Fact]
    public void MultipleTags_OnSameSketch_Work()
    {
        TagStore.SetTag(1, 1, "start");
        TagStore.SetTag(1, 2, "end");
        TagStore.SetTag(1, 3, "center");

        Assert.Equal(1, TagStore.Resolve(1, "start"));
        Assert.Equal(2, TagStore.Resolve(1, "end"));
        Assert.Equal(3, TagStore.Resolve(1, "center"));
    }

    [Fact]
    public void DifferentSketches_SameEntityIndex_DontConflict()
    {
        TagStore.SetTag(1, 3, "eje");
        TagStore.SetTag(5, 3, "profile");

        Assert.Equal("eje", TagStore.GetTag(1, 3));
        Assert.Equal("profile", TagStore.GetTag(5, 3));
        Assert.Null(TagStore.GetTag(2, 3)); // sketch 2 has no tag at index 3
    }
}