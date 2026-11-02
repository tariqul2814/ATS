using ATS_Web_API.Application.Abstractions;
using ATS_Web_API.Application.Options;
using ATS_Web_API.Domain.Entities;
using ATS_Web_API.Domain.Enums;
using ATS_Web_API.Infrastructure.BackgroundServices;
using ATS_Web_API.Infrastructure.Persistence;
using ATS_Web_API.Tests.Fakes;
using FluentAssertions;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using NSubstitute;
using Xunit;

namespace ATS_Web_API.Tests.Infrastructure;

public class StalledAnalysisSweepIntegrationTests : IAsyncLifetime
{
    private static readonly DateTimeOffset Now = new(2026, 10, 13, 12, 0, 0, TimeSpan.Zero);
    private static DateTime NowDt => Now.UtcDateTime;

    private readonly string _dbName = $"AtsSweepTest_{Guid.NewGuid():N}";
    private AppDbContext _ctx = null!;

    private string ConnectionString =>
        $"Server=(localdb)\\MSSQLLocalDB;Database={_dbName};Trusted_Connection=True;TrustServerCertificate=true";

    public async Task InitializeAsync()
    {
        _ctx = new AppDbContext(new DbContextOptionsBuilder<AppDbContext>().UseSqlServer(ConnectionString).Options);
        await _ctx.Database.EnsureCreatedAsync();
    }

    public async Task DisposeAsync()
    {
        await _ctx.Database.EnsureDeletedAsync();
        await _ctx.DisposeAsync();
    }

    [Fact]
    public async Task Sweep_FailsOnlyStalledDispatched_LeavingOthersUntouched()
    {
        var repo = new AnalysisRepository(_ctx);

        var stale = ResumeAnalysis.Create("stale", NowDt.AddMinutes(-30));
        stale.AttachResume("s.pdf", NowDt.AddMinutes(-30));
        stale.MarkDispatched(NowDt.AddMinutes(-30)); // DispatchedAt well past the 10-min cutoff

        var fresh = ResumeAnalysis.Create("fresh", NowDt.AddMinutes(-5));
        fresh.AttachResume("f.pdf", NowDt.AddMinutes(-5));
        fresh.MarkDispatched(NowDt.AddMinutes(-5)); // within the window

        var completed = ResumeAnalysis.Create("done", NowDt.AddMinutes(-30));
        completed.AttachResume("d.pdf", NowDt.AddMinutes(-30));
        completed.MarkDispatched(NowDt.AddMinutes(-30));
        completed.MarkCompleted("{\"score\":90}", NowDt.AddMinutes(-29));

        await repo.AddAsync(stale, default);
        await repo.AddAsync(fresh, default);
        await repo.AddAsync(completed, default);
        await repo.SaveChangesAsync(default);

        var sweep = new StalledAnalysisSweepService(
            repo,
            Substitute.For<IAnalysisStatusCache>(),
            Substitute.For<IAnalysisNotifier>(),
            Options.Create(new AnalysisOptions { DispatchTimeoutMinutes = 10, SweepIntervalSeconds = 60 }),
            new FixedTimeProvider(Now),
            NullLogger<StalledAnalysisSweepService>.Instance);

        var count = await sweep.SweepAsync(default);

        count.Should().Be(1);
        _ctx.ChangeTracker.Clear();

        (await _ctx.Analyses.AsNoTracking().FirstAsync(a => a.Id == stale.Id)).Status
            .Should().Be(AnalysisStatus.Failed);
        (await _ctx.Analyses.AsNoTracking().FirstAsync(a => a.Id == fresh.Id)).Status
            .Should().Be(AnalysisStatus.Dispatched);
        (await _ctx.Analyses.AsNoTracking().FirstAsync(a => a.Id == completed.Id)).Status
            .Should().Be(AnalysisStatus.Completed);
    }
}
