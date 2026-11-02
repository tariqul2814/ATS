using ATS_Web_API.Application.Abstractions;
using ATS_Web_API.Application.Analyses;
using ATS_Web_API.Application.Dtos;
using ATS_Web_API.Application.Options;
using ATS_Web_API.Domain.Entities;
using FluentAssertions;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using NSubstitute;
using NSubstitute.ExceptionExtensions;
using Xunit;

namespace ATS_Web_API.Tests.Application;

public class StartResumeAnalysisHandlerTests
{
    private readonly IAnalysisRepository _repo = Substitute.For<IAnalysisRepository>();
    private readonly IResumeStore _store = Substitute.For<IResumeStore>();
    private readonly IAnalysisDispatcher _dispatcher = Substitute.For<IAnalysisDispatcher>();
    private readonly IAnalysisStatusCache _cache = Substitute.For<IAnalysisStatusCache>();
    private readonly IAnalysisNotifier _notifier = Substitute.For<IAnalysisNotifier>();

    private StartResumeAnalysisHandler CreateHandler(long maxBytes = 5 * 1024 * 1024, int maxJd = 20_000)
    {
        _store.SaveAsync(Arg.Any<Guid>(), Arg.Any<Stream>(), Arg.Any<string>(), Arg.Any<CancellationToken>())
            .Returns(ci => $"{ci.Arg<Guid>()}.pdf");
        _dispatcher.DispatchAsync(Arg.Any<AnalysisDispatchRequest>(), Arg.Any<CancellationToken>())
            .Returns(DispatchOutcome.AcceptedResult());

        return new StartResumeAnalysisHandler(
            _repo, _store, _dispatcher, _cache, _notifier,
            Options.Create(new UploadsOptions { MaxFileSizeBytes = maxBytes, MaxJobDescriptionChars = maxJd }),
            Options.Create(new WebhookOptions { Secret = "0123456789abcdef", PublicCallbackUrl = "https://host/cb" }),
            TimeProvider.System,
            NullLogger<StartResumeAnalysisHandler>.Instance);
    }

    private static ResumeUpload Pdf(long? length = null)
    {
        var bytes = new byte[] { 0x25, 0x50, 0x44, 0x46, 0x2D, 0x31, 0x2E, 0x34 }; // %PDF-1.4
        return new ResumeUpload(new MemoryStream(bytes), "cv.pdf", "application/pdf", length ?? bytes.Length);
    }

    [Fact]
    public async Task MissingFile_ReturnsMissingFile()
    {
        var outcome = await CreateHandler().HandleAsync(null, "jd", default);
        outcome.Error.Should().Be(SubmissionError.MissingFile);
    }

    [Fact]
    public async Task EmptyJobDescription_ReturnsEmptyJobDescription()
    {
        var outcome = await CreateHandler().HandleAsync(Pdf(), "   ", default);
        outcome.Error.Should().Be(SubmissionError.EmptyJobDescription);
    }

    [Fact]
    public async Task OversizedFile_ReturnsFileTooLarge()
    {
        var outcome = await CreateHandler(maxBytes: 4).HandleAsync(Pdf(length: 1000), "jd", default);
        outcome.Error.Should().Be(SubmissionError.FileTooLarge);
    }

    [Fact]
    public async Task JobDescriptionTooLong_ReturnsTooLong()
    {
        var outcome = await CreateHandler(maxJd: 5).HandleAsync(Pdf(), "way too long description", default);
        outcome.Error.Should().Be(SubmissionError.JobDescriptionTooLong);
    }

    [Fact]
    public async Task WrongContentType_ReturnsInvalidFileType()
    {
        var upload = new ResumeUpload(new MemoryStream(new byte[] { 1, 2, 3, 4 }), "note.txt", "text/plain", 4);
        var outcome = await CreateHandler().HandleAsync(upload, "jd", default);
        outcome.Error.Should().Be(SubmissionError.InvalidFileType);
    }

    [Fact]
    public async Task DeclaredPdf_ButWrongSignature_ReturnsInvalidFileType()
    {
        var upload = new ResumeUpload(new MemoryStream(new byte[] { 0x00, 0x01, 0x02, 0x03 }), "cv.pdf", "application/pdf", 4);
        var outcome = await CreateHandler().HandleAsync(upload, "jd", default);
        outcome.Error.Should().Be(SubmissionError.InvalidFileType);
    }

    [Fact]
    public async Task ValidPdf_DispatchAccepted_MarksDispatched()
    {
        var handler = CreateHandler();

        var outcome = await handler.HandleAsync(Pdf(), "Senior .NET engineer", default);

        outcome.Succeeded.Should().BeTrue();
        outcome.Accepted!.Status.Should().Be("Dispatched");
        outcome.Accepted.AnalysisId.Should().NotBe(Guid.Empty);
        await _repo.Received().AddAsync(Arg.Any<ResumeAnalysis>(), Arg.Any<CancellationToken>());
        await _store.Received(1).SaveAsync(Arg.Any<Guid>(), Arg.Any<Stream>(), ".pdf", Arg.Any<CancellationToken>());
        await _dispatcher.Received(1).DispatchAsync(Arg.Any<AnalysisDispatchRequest>(), Arg.Any<CancellationToken>());
    }

    [Fact]
    public async Task DispatchFailed_MarksFailed_NeverPending()
    {
        _store.SaveAsync(Arg.Any<Guid>(), Arg.Any<Stream>(), Arg.Any<string>(), Arg.Any<CancellationToken>())
            .Returns(ci => $"{ci.Arg<Guid>()}.pdf");
        _dispatcher.DispatchAsync(Arg.Any<AnalysisDispatchRequest>(), Arg.Any<CancellationToken>())
            .Returns(DispatchOutcome.Failed("fastapi_status_500"));

        var handler = new StartResumeAnalysisHandler(
            _repo, _store, _dispatcher, _cache, _notifier,
            Options.Create(new UploadsOptions()),
            Options.Create(new WebhookOptions { Secret = "0123456789abcdef", PublicCallbackUrl = "https://host/cb" }),
            TimeProvider.System,
            NullLogger<StartResumeAnalysisHandler>.Instance);

        var outcome = await handler.HandleAsync(Pdf(), "jd", default);

        // Client still gets a 202 + id, but the analysis itself is Failed (Req 5.1, 10.3, 10.5).
        outcome.Succeeded.Should().BeTrue();
        outcome.Accepted!.Status.Should().Be("Failed");
    }

    [Fact]
    public async Task StorageFailure_ReturnsStorageFailure_AndDoesNotDispatch()
    {
        _store.SaveAsync(Arg.Any<Guid>(), Arg.Any<Stream>(), Arg.Any<string>(), Arg.Any<CancellationToken>())
            .ThrowsAsync(new IOException("disk full"));

        var handler = new StartResumeAnalysisHandler(
            _repo, _store, _dispatcher, _cache, _notifier,
            Options.Create(new UploadsOptions()),
            Options.Create(new WebhookOptions { Secret = "0123456789abcdef", PublicCallbackUrl = "https://host/cb" }),
            TimeProvider.System,
            NullLogger<StartResumeAnalysisHandler>.Instance);

        var outcome = await handler.HandleAsync(Pdf(), "jd", default);

        outcome.Error.Should().Be(SubmissionError.StorageFailure);
        await _repo.Received(2).SaveChangesAsync(Arg.Any<CancellationToken>()); // Pending, then Failed
        await _dispatcher.DidNotReceive().DispatchAsync(Arg.Any<AnalysisDispatchRequest>(), Arg.Any<CancellationToken>());
    }
}
