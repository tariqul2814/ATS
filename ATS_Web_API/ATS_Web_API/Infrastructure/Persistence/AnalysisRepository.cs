using ATS_Web_API.Application;
using ATS_Web_API.Application.Abstractions;
using ATS_Web_API.Domain.Entities;
using ATS_Web_API.Domain.Enums;
using Microsoft.EntityFrameworkCore;

namespace ATS_Web_API.Infrastructure.Persistence;

public sealed class AnalysisRepository : IAnalysisRepository
{
    private readonly AppDbContext _db;

    public AnalysisRepository(AppDbContext db) => _db = db;

    public Task<ResumeAnalysis?> GetAsync(Guid analysisId, CancellationToken ct) =>
        _db.Analyses.FirstOrDefaultAsync(a => a.Id == analysisId, ct);

    public async Task AddAsync(ResumeAnalysis analysis, CancellationToken ct) =>
        await _db.Analyses.AddAsync(analysis, ct);

    public async Task SaveChangesAsync(CancellationToken ct)
    {
        try
        {
            await _db.SaveChangesAsync(ct);
        }
        catch (DbUpdateConcurrencyException ex)
        {
            throw new ConcurrencyConflictException(ex);
        }
    }

    public async Task<IReadOnlyList<ResumeAnalysis>> GetManyAsync(IEnumerable<Guid> ids, CancellationToken ct)
    {
        var requested = ids.Distinct().ToArray();
        return await _db.Analyses
            .Where(a => requested.Contains(a.Id))
            .OrderByDescending(a => a.CreatedAt)
            .ToListAsync(ct);
    }

    public async Task<IReadOnlyList<ResumeAnalysis>> GetStalledDispatchedAsync(DateTime olderThanUtc, CancellationToken ct) =>
        await _db.Analyses
            .Where(a => a.Status == AnalysisStatus.Dispatched && a.DispatchedAt < olderThanUtc)
            .ToListAsync(ct);
}
