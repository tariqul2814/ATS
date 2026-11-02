using System.ComponentModel.DataAnnotations;

namespace ATS_Web_API.Application.Options;

/// <summary>Timing for dispatch timeout and the stalled-analysis sweeper (Requirement 11, 15).</summary>
public sealed class AnalysisOptions
{
    public const string SectionName = "Analysis";

    /// <summary>How long an analysis may remain Dispatched before the sweeper fails it.</summary>
    [Range(1, 1440)]
    public int DispatchTimeoutMinutes { get; init; } = 10;

    /// <summary>How often the sweeper runs.</summary>
    [Range(5, 3600)]
    public int SweepIntervalSeconds { get; init; } = 60;
}
