using ATS_Web_API.Domain.Entities;

namespace ATS_Web_API.Application.Dtos;

/// <summary>Snapshot of an analysis for the status cache, push notifications, and the status endpoint.</summary>
public sealed record AnalysisStatusDto(
    Guid AnalysisId,
    string Status,
    DateTime CreatedAt,
    DateTime UpdatedAt,
    string? ResultJson,
    string? Error)
{
    public static AnalysisStatusDto From(ResumeAnalysis a) =>
        new(a.Id, a.Status.ToString(), a.CreatedAt, a.UpdatedAt, a.ResultJson, a.Error);
}
