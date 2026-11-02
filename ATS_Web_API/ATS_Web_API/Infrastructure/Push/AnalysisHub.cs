using Microsoft.AspNetCore.SignalR;

namespace ATS_Web_API.Infrastructure.Push;

/// <summary>
/// SignalR hub clients connect to for real-time analysis updates (Requirement 12.2).
/// A client subscribes with its analysis id and is added to a per-analysis group.
/// </summary>
public sealed class AnalysisHub : Hub
{
    public Task SubscribeToAnalysis(Guid analysisId) =>
        Groups.AddToGroupAsync(Context.ConnectionId, GroupName(analysisId));

    public static string GroupName(Guid analysisId) => $"analysis-{analysisId}";
}
