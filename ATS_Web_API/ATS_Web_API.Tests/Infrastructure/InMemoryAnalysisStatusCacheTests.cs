using ATS_Web_API.Application.Dtos;
using ATS_Web_API.Infrastructure.Cache;
using FluentAssertions;
using Microsoft.Extensions.Caching.Memory;
using Xunit;

namespace ATS_Web_API.Tests.Infrastructure;

public class InMemoryAnalysisStatusCacheTests
{
    private static InMemoryAnalysisStatusCache NewCache() =>
        new(new MemoryCache(new MemoryCacheOptions()));

    private static AnalysisStatusDto Dto(Guid id, string status) =>
        new(id, status, DateTime.UtcNow, DateTime.UtcNow, null, null);

    [Fact]
    public void TryGet_Miss_ReturnsFalse()
    {
        var cache = NewCache();
        cache.TryGet(Guid.NewGuid(), out var dto).Should().BeFalse();
        dto.Should().BeNull();
    }

    [Fact]
    public void Set_ThenTryGet_ReturnsLatest()
    {
        var cache = NewCache();
        var id = Guid.NewGuid();

        cache.Set(Dto(id, "Pending"));
        cache.Set(Dto(id, "Dispatched")); // overwrite with newer status

        cache.TryGet(id, out var dto).Should().BeTrue();
        dto!.Status.Should().Be("Dispatched");
    }
}
