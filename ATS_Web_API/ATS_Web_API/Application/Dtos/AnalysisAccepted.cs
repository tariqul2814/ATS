namespace ATS_Web_API.Application.Dtos;

/// <summary>202 response body for an accepted submission (Requirement 5.1).</summary>
public sealed record AnalysisAccepted(Guid AnalysisId, string Status);
