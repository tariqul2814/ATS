using ATS_Web_API.Application.Dtos;
using ATS_Web_API.Infrastructure.Push;
using FluentAssertions;
using Microsoft.AspNetCore.SignalR;
using NSubstitute;
using Xunit;

namespace ATS_Web_API.Tests.Infrastructure;

public class SignalRAnalysisNotifierTests
{
    [Fact]
    public async Task NotifyAsync_SendsAnalysisUpdated_ToTheAnalysisGroup()
    {
        var hub = Substitute.For<IHubContext<AnalysisHub>>();
        var clients = Substitute.For<IHubClients>();
        var proxy = Substitute.For<IClientProxy>();
        hub.Clients.Returns(clients);
        clients.Group(Arg.Any<string>()).Returns(proxy);

        var id = Guid.NewGuid();
        var dto = new AnalysisStatusDto(id, "Completed", DateTime.UtcNow, DateTime.UtcNow, "{\"score\":1}", null);

        await new SignalRAnalysisNotifier(hub).NotifyAsync(dto, default);

        clients.Received().Group(AnalysisHub.GroupName(id));
        await proxy.Received().SendCoreAsync(
            SignalRAnalysisNotifier.EventName,
            Arg.Is<object?[]>(a => a.Length == 1 && ReferenceEquals(a[0], dto)),
            Arg.Any<CancellationToken>());
    }
}
