using ATS_Web_API.Application;
using ATS_Web_API.Application.Abstractions;
using ATS_Web_API.Application.Dtos;
using ATS_Web_API.Application.Options;
using ATS_Web_API.Domain.Entities;
using ATS_Web_API.Domain.Enums;
using ATS_Web_API.Infrastructure.BackgroundServices;
using ATS_Web_API.Tests.Fakes;
using FluentAssertions;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using NSubstitute;
using NSubstitute.ExceptionExtensions;
using Xunit;

namespace ATS_Web_API.Tests.Infrastructure;

public class StalledAnalysisSweepServiceTests
{
    private static readonly DateTimeOffset Now = new(2026, 10, 13, 12, 0, 0, TimeSpan.Zero);

    private readonly IAnalysisRepository _repo = Substitute.For<IAnalysisRepository>();
    private readonly IAnalysisStatusCache _cache = Substitute.For<IAnalysisStatusCache>();
    private readonly IAnalysisNotifier _notifier = Substitute.For<IAnalysisNotifier>();

    private StalledAnalysisSweepService Create() =>
        new(_repo, _cache, _notifier,
            Options.Create(new AnalysisOptions { DispatchTimeoutMinutes = 10, SweepIntervalSeconds = 60 }),
            new FixedTimeProvider(Now),
            NullLogger<StalledAnalysisSweepService>.Instance);

    private static ResumeAnalysis StaleDispatched()
    {
        var a = ResumeAnalysis.Create("jd", DateTime.UtcNow.AddMinutes(-30));
        a.AttachResume("x.pdf", DateTime.UtcNow.AddMinutes(-30));
        a.MarkDispatched(DateTime.UtcNow.AddMinutes(-30));
        return a;
    }

    [Fact]
    public async Task Sweep_FailsStalledAnalysis_AndNotifies()
    {
        var stale = StaleDispatched();
        _repo.GetStalledDispatchedAsync(Arg.Any<DateTime>(), Arg.Any<CancellationToken>())
            .Returns(new List<ResumeAnalysis> { stale });

        var count = await Create().SweepAsync(default);

        count.Should().Be(1);
        stale.Status.Should().Be(AnalysisStatus.Failed);
        stale.Error.Should().Be("dispatch_timeout");
        await _repo.Received(1).SaveChangesAsync(Arg.Any<CancellationToken>());
        _cache.Received(1).Set(Arg.Any<AnalysisStatusDto>());
        await _notifier.Received(1).NotifyAsync(Arg.Any<AnalysisStatusDto>(), Arg.Any<CancellationToken>());
    }

    [Fact]
    public async Task Sweep_ConcurrencyConflict_SkipsWithoutNotifying()
    {
        var stale = StaleDispatched();
        _repo.GetStalledDispatchedAsync(Arg.Any<DateTime>(), Arg.Any<CancellationToken>())
            .Returns(new List<ResumeAnalysis> { stale });
        _repo.SaveChangesAsync(Arg.Any<CancellationToken>())
            .ThrowsAsync(new ConcurrencyConflictException(new Exception("row version")));

        var count = await Create().SweepAsync(default);

        count.Should().Be(0);
        await _notifier.DidNotReceive().NotifyAsync(Arg.Any<AnalysisStatusDto>(), Arg.Any<CancellationToken>());
    }
}
