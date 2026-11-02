using ATS_Web_API.Application.Abstractions;
using ATS_Web_API.Application.Dtos;
using Microsoft.AspNetCore.SignalR;

namespace ATS_Web_API.Infrastructure.Push;

/// <summary>Pushes an <c>analysisUpdated</c> message to the analysis's SignalR group (Requirement 12.1).</summary>
public sealed class SignalRAnalysisNotifier : IAnalysisNotifier
{
    public const string EventName = "analysisUpdated";

    private readonly IHubContext<AnalysisHub> _hub;

    public SignalRAnalysisNotifier(IHubContext<AnalysisHub> hub) => _hub = hub;

    public Task NotifyAsync(AnalysisStatusDto status, CancellationToken ct) =>
        _hub.Clients.Group(AnalysisHub.GroupName(status.AnalysisId)).SendAsync(EventName, status, ct);
}
