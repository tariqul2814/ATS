using ATS_Web_API.Domain.Entities;
using ATS_Web_API.Infrastructure.Persistence;
using FluentAssertions;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace ATS_Web_API.Tests.Infrastructure;

/// <summary>
/// Integration tests against SQL Server LocalDB (Task 4.4). Each test class instance gets its own
/// throwaway database created from the model and dropped on dispose.
/// </summary>
public class AnalysisRepositoryTests : IAsyncLifetime
{
    private static readonly DateTime Now = new(2026, 10, 13, 12, 0, 0, DateTimeKind.Utc);

    private readonly string _dbName = $"AtsTest_{Guid.NewGuid():N}";
    private AppDbContext _ctx = null!;
    private AnalysisRepository _repo = null!;

    private string ConnectionString =>
        $"Server=(localdb)\\MSSQLLocalDB;Database={_dbName};Trusted_Connection=True;TrustServerCertificate=true";

    public async Task InitializeAsync()
    {
        _ctx = new AppDbContext(new DbContextOptionsBuilder<AppDbContext>().UseSqlServer(ConnectionString).Options);
        await _ctx.Database.EnsureCreatedAsync();
        _repo = new AnalysisRepository(_ctx);
    }

    public async Task DisposeAsync()
    {
        await _ctx.Database.EnsureDeletedAsync();
        await _ctx.DisposeAsync();
    }

    [Fact]
    public async Task Add_And_Get_RoundTripsThroughDatabase()
    {
        var analysis = ResumeAnalysis.Create("Senior .NET engineer", Now);
        analysis.AttachResume($"{analysis.Id}.pdf", Now);

        await _repo.AddAsync(analysis, default);
        await _repo.SaveChangesAsync(default);
        _ctx.ChangeTracker.Clear(); // force a real read from the database

        var loaded = await _repo.GetAsync(analysis.Id, default);

        loaded.Should().NotBeNull();
        loaded!.JobDescription.Should().Be("Senior .NET engineer");
        loaded.ResumeFileReference.Should().Be($"{analysis.Id}.pdf");
        loaded.RowVersion.Should().NotBeEmpty(); // populated by SQL Server
    }

    [Fact]
    public async Task GetStalledDispatched_ReturnsOnlyDispatchedOlderThanCutoff()
    {
        var staleDispatched = ResumeAnalysis.Create("stale", Now.AddMinutes(-20));
        staleDispatched.MarkDispatched(Now.AddMinutes(-20));

        var freshDispatched = ResumeAnalysis.Create("fresh", Now.AddMinutes(-5));
        freshDispatched.MarkDispatched(Now.AddMinutes(-5));

        var stillPending = ResumeAnalysis.Create("pending", Now);

        await _repo.AddAsync(staleDispatched, default);
        await _repo.AddAsync(freshDispatched, default);
        await _repo.AddAsync(stillPending, default);
        await _repo.SaveChangesAsync(default);
        _ctx.ChangeTracker.Clear();

        var cutoff = Now.AddMinutes(-10);
        var stalled = await _repo.GetStalledDispatchedAsync(cutoff, default);

        stalled.Select(a => a.Id).Should().ContainSingle()
            .Which.Should().Be(staleDispatched.Id);
    }

    [Fact]
    public async Task GetMany_ReturnsRequestedIdsNewestFirst_AndOmitsUnknown()
    {
        var older = ResumeAnalysis.Create("older", Now.AddMinutes(-10));
        var newer = ResumeAnalysis.Create("newer", Now);

        await _repo.AddAsync(older, default);
        await _repo.AddAsync(newer, default);
        await _repo.SaveChangesAsync(default);
        _ctx.ChangeTracker.Clear();

        var result = await _repo.GetManyAsync(new[] { older.Id, newer.Id, Guid.NewGuid() }, default);

        result.Select(a => a.Id).Should().Equal(newer.Id, older.Id); // newest first, unknown omitted
    }
}
