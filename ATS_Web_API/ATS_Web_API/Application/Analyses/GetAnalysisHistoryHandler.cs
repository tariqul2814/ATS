using ATS_Web_API.Application.Abstractions;
using ATS_Web_API.Application.Dtos;

namespace ATS_Web_API.Application.Analyses;

/// <summary>
/// Resolves history ONLY for the GUIDs supplied by the caller, newest first; unknown ids are
/// simply absent (Requirement 14). There is no list-all path.
/// </summary>
public class GetAnalysisHistoryHandler
{
    private readonly IAnalysisRepository _repository;

    public GetAnalysisHistoryHandler(IAnalysisRepository repository) => _repository = repository;

    public virtual async Task<IReadOnlyList<AnalysisHistoryItem>> GetAsync(IEnumerable<Guid> ids, CancellationToken ct)
    {
        var analyses = await _repository.GetManyAsync(ids, ct); // ordered newest-first by the repository
        return analyses
            .Select(a => new AnalysisHistoryItem(a.Id, a.Status.ToString(), a.CreatedAt, a.ResultJson is not null))
            .ToList();
    }
}
