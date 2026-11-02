using ATS_Web_API.Application.Dtos;

namespace ATS_Web_API.Application.Abstractions;

/// <summary>Result of attempting to hand an analysis to FastAPI (Requirement 4.2, 4.5).</summary>
public sealed record DispatchOutcome(bool Accepted, string? FailureReason)
{
    public static DispatchOutcome AcceptedResult() => new(true, null);
    public static DispatchOutcome Failed(string reason) => new(false, reason);
}

/// <summary>Dispatch port for the external FastAPI analysis service (Requirement 4, 10).</summary>
public interface IAnalysisDispatcher
{
    Task<DispatchOutcome> DispatchAsync(AnalysisDispatchRequest request, CancellationToken ct);
}
