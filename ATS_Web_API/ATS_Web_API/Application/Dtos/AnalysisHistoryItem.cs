namespace ATS_Web_API.Application.Dtos;

/// <summary>History list item for a single analysis (Requirement 14.2).</summary>
public sealed record AnalysisHistoryItem(
    Guid AnalysisId,
    string Status,
    DateTime CreatedAt,
    bool HasResult);
