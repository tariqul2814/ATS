using System.Text.Json;

namespace ATS_Web_API.Application.Dtos;

/// <summary>
/// Body FastAPI posts to the webhook (Requirement 6). <see cref="Result"/> carries the opaque
/// analysis document (stored as-is when Completed); <see cref="Error"/> is set when Failed.
/// </summary>
public sealed record AnalysisResultCallback(
    Guid AnalysisId,
    string? Status,
    JsonElement? Result,
    string? Error);
