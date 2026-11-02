using ATS_Web_API.Application.Abstractions;
using ATS_Web_API.Application.Dtos;

namespace ATS_Web_API.Application.Analyses;

/// <summary>
/// Returns an analysis status cache-first, falling back to the database on a miss and
/// repopulating the cache (Requirement 13.2, 13.3). Returns null when unknown.
/// </summary>
public class GetAnalysisStatusHandler
{
    private readonly IAnalysisRepository _repository;
    private readonly IAnalysisStatusCache _cache;

    public GetAnalysisStatusHandler(IAnalysisRepository repository, IAnalysisStatusCache cache)
    {
        _repository = repository;
        _cache = cache;
    }

    public virtual async Task<AnalysisStatusDto?> GetAsync(Guid analysisId, CancellationToken ct)
    {
        if (_cache.TryGet(analysisId, out var cached) && cached is not null)
            return cached;

        var analysis = await _repository.GetAsync(analysisId, ct);
        if (analysis is null)
            return null;

        var dto = AnalysisStatusDto.From(analysis);
        _cache.Set(dto);
        return dto;
    }
}
