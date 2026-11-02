using ATS_Web_API.Application.Abstractions;
using ATS_Web_API.Application.Analyses;
using ATS_Web_API.Application.Dtos;
using ATS_Web_API.Domain.Entities;
using FluentAssertions;
using NSubstitute;
using Xunit;

namespace ATS_Web_API.Tests.Application;

public class GetAnalysisHandlersTests
{
    private readonly IAnalysisRepository _repo = Substitute.For<IAnalysisRepository>();
    private readonly IAnalysisStatusCache _cache = Substitute.For<IAnalysisStatusCache>();

    private static readonly DateTime T = new(2026, 10, 13, 12, 0, 0, DateTimeKind.Utc);

    // ---- GetAnalysisStatusHandler (Req 13) ----

    [Fact]
    public async Task Status_CacheHit_ReturnsCached_WithoutHittingDb()
    {
        var id = Guid.NewGuid();
        var cached = new AnalysisStatusDto(id, "Completed", T, T, "{\"score\":1}", null);
        _cache.TryGet(id, out Arg.Any<AnalysisStatusDto?>())
            .Returns(ci => { ci[1] = cached; return true; });

        var result = await new GetAnalysisStatusHandler(_repo, _cache).GetAsync(id, default);

        result.Should().BeSameAs(cached);
        await _repo.DidNotReceive().GetAsync(Arg.Any<Guid>(), Arg.Any<CancellationToken>());
    }

    [Fact]
    public async Task Status_CacheMiss_FallsBackToDb_AndRepopulates()
    {
        var analysis = ResumeAnalysis.Create("jd", T);
        _cache.TryGet(analysis.Id, out Arg.Any<AnalysisStatusDto?>())
            .Returns(ci => { ci[1] = null; return false; });
        _repo.GetAsync(analysis.Id, Arg.Any<CancellationToken>()).Returns(analysis);

        var result = await new GetAnalysisStatusHandler(_repo, _cache).GetAsync(analysis.Id, default);

        result!.AnalysisId.Should().Be(analysis.Id);
        _cache.Received(1).Set(Arg.Is<AnalysisStatusDto>(d => d.AnalysisId == analysis.Id));
    }

    [Fact]
    public async Task Status_Unknown_ReturnsNull()
    {
        var id = Guid.NewGuid();
        _cache.TryGet(id, out Arg.Any<AnalysisStatusDto?>()).Returns(ci => { ci[1] = null; return false; });
        _repo.GetAsync(id, Arg.Any<CancellationToken>()).Returns((ResumeAnalysis?)null);

        (await new GetAnalysisStatusHandler(_repo, _cache).GetAsync(id, default)).Should().BeNull();
    }

    // ---- GetAnalysisHistoryHandler (Req 14) ----

    [Fact]
    public async Task History_MapsItems_WithHasResultFlag()
    {
        var completed = ResumeAnalysis.Create("c", T);
        completed.AttachResume("c.pdf", T);
        completed.MarkDispatched(T);
        completed.MarkCompleted("{\"score\":5}", T);

        var dispatched = ResumeAnalysis.Create("d", T);
        dispatched.AttachResume("d.pdf", T);
        dispatched.MarkDispatched(T);

        _repo.GetManyAsync(Arg.Any<IEnumerable<Guid>>(), Arg.Any<CancellationToken>())
            .Returns(new List<ResumeAnalysis> { completed, dispatched });

        var items = await new GetAnalysisHistoryHandler(_repo).GetAsync(new[] { completed.Id, dispatched.Id }, default);

        items.Should().HaveCount(2);
        items.Single(i => i.AnalysisId == completed.Id).HasResult.Should().BeTrue();
        items.Single(i => i.AnalysisId == dispatched.Id).HasResult.Should().BeFalse();
    }
}
