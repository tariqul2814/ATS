using ATS_Web_API.Domain.Entities;

namespace ATS_Web_API.Application.Abstractions;

/// <summary>Persistence port for <see cref="ResumeAnalysis"/> (Requirement 3, 9, 11, 14).</summary>
public interface IAnalysisRepository
{
    Task<ResumeAnalysis?> GetAsync(Guid analysisId, CancellationToken ct);

    Task AddAsync(ResumeAnalysis analysis, CancellationToken ct);

    /// <summary>Persists tracked changes; surfaces concurrency conflicts to the caller (Req 9.6).</summary>
    Task SaveChangesAsync(CancellationToken ct);

    /// <summary>Resolves only the supplied ids, newest first; unknown ids are simply absent (Req 14).</summary>
    Task<IReadOnlyList<ResumeAnalysis>> GetManyAsync(IEnumerable<Guid> ids, CancellationToken ct);

    /// <summary>Dispatched analyses whose DispatchedAt is older than the cutoff (Req 11).</summary>
    Task<IReadOnlyList<ResumeAnalysis>> GetStalledDispatchedAsync(DateTime olderThanUtc, CancellationToken ct);
}
