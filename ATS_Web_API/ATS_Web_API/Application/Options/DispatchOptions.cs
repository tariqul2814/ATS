using System.ComponentModel.DataAnnotations;

namespace ATS_Web_API.Application.Options;

/// <summary>Retry policy for dispatching to FastAPI (Requirement 10.2, Q4).</summary>
public sealed class DispatchOptions
{
    public const string SectionName = "Dispatch";

    [Range(0, 10)]
    public int RetryCount { get; init; } = 3;

    [Range(1, 60)]
    public int BaseDelaySeconds { get; init; } = 2;
}
