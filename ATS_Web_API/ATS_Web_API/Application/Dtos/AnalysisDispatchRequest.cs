namespace ATS_Web_API.Application.Dtos;

/// <summary>Payload POSTed to the FastAPI service to request an analysis (Requirement 4.1).</summary>
public sealed record AnalysisDispatchRequest(
    Guid AnalysisId,
    string ResumeFileReference,
    string JobDescription,
    string CallbackUrl);
