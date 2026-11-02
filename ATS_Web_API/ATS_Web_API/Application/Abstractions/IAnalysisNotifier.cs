using ATS_Web_API.Application.Dtos;

namespace ATS_Web_API.Application.Abstractions;

/// <summary>Push port: notifies subscribed clients of an analysis outcome in real time (Requirement 12).</summary>
public interface IAnalysisNotifier
{
    Task NotifyAsync(AnalysisStatusDto status, CancellationToken ct);
}
