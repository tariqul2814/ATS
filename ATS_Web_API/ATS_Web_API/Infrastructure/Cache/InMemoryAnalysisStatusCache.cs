using ATS_Web_API.Application.Abstractions;
using ATS_Web_API.Application.Dtos;
using Microsoft.Extensions.Caching.Memory;

namespace ATS_Web_API.Infrastructure.Cache;

/// <summary>
/// In-process status cache over <see cref="IMemoryCache"/> (Requirement 12.3). Non-durable: the DB
/// remains the source of truth, so a lost entry never loses data (Req 12.7, 13.3).
/// </summary>
public sealed class InMemoryAnalysisStatusCache : IAnalysisStatusCache
{
    private readonly IMemoryCache _cache;

    public InMemoryAnalysisStatusCache(IMemoryCache cache) => _cache = cache;

    private static string Key(Guid id) => $"analysis-status:{id}";

    public void Set(AnalysisStatusDto status) => _cache.Set(Key(status.AnalysisId), status);

    public bool TryGet(Guid analysisId, out AnalysisStatusDto? status) =>
        _cache.TryGetValue(Key(analysisId), out status);
}
