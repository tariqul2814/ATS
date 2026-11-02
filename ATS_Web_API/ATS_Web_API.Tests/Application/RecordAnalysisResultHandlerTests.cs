using System.Text.Json;
using ATS_Web_API.Application;
using ATS_Web_API.Application.Abstractions;
using ATS_Web_API.Application.Analyses;
using ATS_Web_API.Application.Dtos;
using ATS_Web_API.Domain.Entities;
using ATS_Web_API.Domain.Enums;
using FluentAssertions;
using Microsoft.Extensions.Logging.Abstractions;
using NSubstitute;
using NSubstitute.ExceptionExtensions;
using Xunit;

namespace ATS_Web_API.Tests.Application;

public class RecordAnalysisResultHandlerTests
{
    private readonly IAnalysisRepository _repo = Substitute.For<IAnalysisRepository>();
    private readonly IAnalysisStatusCache _cache = Substitute.For<IAnalysisStatusCache>();
    private readonly IAnalysisNotifier _notifier = Substitute.For<IAnalysisNotifier>();

    private RecordAnalysisResultHandler Handler() =>
        new(_repo, _cache, _notifier, TimeProvider.System, NullLogger<RecordAnalysisResultHandler>.Instance);

    private static readonly DateTime T = new(2026, 10, 13, 12, 0, 0, DateTimeKind.Utc);

    private static ResumeAnalysis Dispatched()
    {
        var a = ResumeAnalysis.Create("jd", T);
        a.AttachResume("x.pdf", T);
        a.MarkDispatched(T);
        return a;
    }

    private static JsonElement Json(string raw) => JsonDocument.Parse(raw).RootElement.Clone();

    private void RepoReturns(ResumeAnalysis a) =>
        _repo.GetAsync(a.Id, Arg.Any<CancellationToken>()).Returns(a);

    [Fact]
    public async Task Null_IsInvalid()
    {
        (await Handler().HandleAsync(null, default)).Should().Be(CallbackResult.Invalid);
    }

    [Fact]
    public async Task UnknownStatus_IsInvalid()
    {
        var cb = new AnalysisResultCallback(Guid.NewGuid(), "Weird", null, null);
        (await Handler().HandleAsync(cb, default)).Should().Be(CallbackResult.Invalid);
    }

    [Fact]
    public async Task CompletedWithoutResult_IsInvalid()
    {
        var cb = new AnalysisResultCallback(Guid.NewGuid(), "Completed", null, null);
        (await Handler().HandleAsync(cb, default)).Should().Be(CallbackResult.Invalid);
    }

    [Fact]
    public async Task UnknownId_IsNotFound()
    {
        _repo.GetAsync(Arg.Any<Guid>(), Arg.Any<CancellationToken>()).Returns((ResumeAnalysis?)null);
        var cb = new AnalysisResultCallback(Guid.NewGuid(), "Completed", Json("{\"score\":1}"), null);

        (await Handler().HandleAsync(cb, default)).Should().Be(CallbackResult.NotFound);
    }

    [Fact]
    public async Task Completed_IsApplied_AndRecordsResult()
    {
        var analysis = Dispatched();
        RepoReturns(analysis);
        var cb = new AnalysisResultCallback(analysis.Id, "Completed", Json("{\"score\":80}"), null);

        var result = await Handler().HandleAsync(cb, default);

        result.Should().Be(CallbackResult.Applied);
        analysis.Status.Should().Be(AnalysisStatus.Completed);
        analysis.ResultJson.Should().Contain("80");
        await _repo.Received(1).SaveChangesAsync(Arg.Any<CancellationToken>());
        _cache.Received(1).Set(Arg.Any<AnalysisStatusDto>());
    }

    [Fact]
    public async Task Failed_IsApplied_AndRecordsError()
    {
        var analysis = Dispatched();
        RepoReturns(analysis);
        var cb = new AnalysisResultCallback(analysis.Id, "Failed", null, "parse_failed");

        var result = await Handler().HandleAsync(cb, default);

        result.Should().Be(CallbackResult.Applied);
        analysis.Status.Should().Be(AnalysisStatus.Failed);
        analysis.Error.Should().Be("parse_failed");
    }

    [Fact]
    public async Task AlreadyTerminal_IsDuplicateIgnored_WithNoSave()
    {
        var analysis = Dispatched();
        analysis.MarkCompleted("{\"score\":99}", T);
        RepoReturns(analysis);
        var cb = new AnalysisResultCallback(analysis.Id, "Completed", Json("{\"score\":1}"), null);

        var result = await Handler().HandleAsync(cb, default);

        result.Should().Be(CallbackResult.DuplicateIgnored);
        analysis.ResultJson.Should().Contain("99"); // unchanged
        await _repo.DidNotReceive().SaveChangesAsync(Arg.Any<CancellationToken>());
    }

    [Fact]
    public async Task ConcurrencyConflict_IsDuplicateIgnored()
    {
        var analysis = Dispatched();
        RepoReturns(analysis);
        _repo.SaveChangesAsync(Arg.Any<CancellationToken>())
            .ThrowsAsync(new ConcurrencyConflictException(new Exception("row version")));
        var cb = new AnalysisResultCallback(analysis.Id, "Completed", Json("{\"score\":80}"), null);

        var result = await Handler().HandleAsync(cb, default);

        result.Should().Be(CallbackResult.DuplicateIgnored);
    }
}
