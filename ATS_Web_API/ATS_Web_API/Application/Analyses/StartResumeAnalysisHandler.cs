using ATS_Web_API.Application.Abstractions;
using ATS_Web_API.Application.Dtos;
using ATS_Web_API.Application.Options;
using ATS_Web_API.Domain.Entities;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace ATS_Web_API.Application.Analyses;

/// <summary>
/// Validates a submission, persists a Pending analysis, and stores the résumé file (Requirement 1, 2, 3).
/// Dispatch to FastAPI is layered on in Task 8.
/// </summary>
public class StartResumeAnalysisHandler
{
    private const string PdfContentType = "application/pdf";
    private const string DocxContentType = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

    private static readonly byte[] PdfMagic = { 0x25, 0x50, 0x44, 0x46 };        // %PDF
    private static readonly byte[] ZipMagic = { 0x50, 0x4B, 0x03, 0x04 };        // PK.. (DOCX is a zip)

    private readonly IAnalysisRepository _repository;
    private readonly IResumeStore _resumeStore;
    private readonly IAnalysisDispatcher _dispatcher;
    private readonly IAnalysisStatusCache _cache;
    private readonly IAnalysisNotifier _notifier;
    private readonly UploadsOptions _uploads;
    private readonly WebhookOptions _webhook;
    private readonly TimeProvider _time;
    private readonly ILogger<StartResumeAnalysisHandler> _logger;

    public StartResumeAnalysisHandler(
        IAnalysisRepository repository,
        IResumeStore resumeStore,
        IAnalysisDispatcher dispatcher,
        IAnalysisStatusCache cache,
        IAnalysisNotifier notifier,
        IOptions<UploadsOptions> uploads,
        IOptions<WebhookOptions> webhook,
        TimeProvider time,
        ILogger<StartResumeAnalysisHandler> logger)
    {
        _repository = repository;
        _resumeStore = resumeStore;
        _dispatcher = dispatcher;
        _cache = cache;
        _notifier = notifier;
        _uploads = uploads.Value;
        _webhook = webhook.Value;
        _time = time;
        _logger = logger;
    }

    public virtual async Task<SubmissionOutcome> HandleAsync(ResumeUpload? file, string? jobDescription, CancellationToken ct)
    {
        // --- Validation (Requirement 1) ---
        if (file is null)
            return SubmissionOutcome.Fail(SubmissionError.MissingFile, "A résumé file is required.");

        if (file.Length <= 0)
            return SubmissionOutcome.Fail(SubmissionError.MissingFile, "The uploaded file is empty.");

        if (file.Length > _uploads.MaxFileSizeBytes)
            return SubmissionOutcome.Fail(SubmissionError.FileTooLarge,
                $"File exceeds the maximum size of {_uploads.MaxFileSizeBytes} bytes.");

        if (string.IsNullOrWhiteSpace(jobDescription))
            return SubmissionOutcome.Fail(SubmissionError.EmptyJobDescription, "A job description is required.");

        if (jobDescription.Length > _uploads.MaxJobDescriptionChars)
            return SubmissionOutcome.Fail(SubmissionError.JobDescriptionTooLong,
                $"Job description exceeds {_uploads.MaxJobDescriptionChars} characters.");

        // Buffer the content (bounded by the size check above) so we can inspect the signature
        // and then store it, independent of stream seekability.
        using var buffer = new MemoryStream();
        await file.Content.CopyToAsync(buffer, ct);
        var bytes = buffer.ToArray();

        if (!TryResolveFileType(file.ContentType, bytes, out var extension))
            return SubmissionOutcome.Fail(SubmissionError.InvalidFileType,
                "Only PDF or DOCX files are accepted.");

        var now = _time.GetUtcNow().UtcDateTime;

        // --- Persist Pending before any external I/O (Requirement 3.3, 3.4) ---
        var analysis = ResumeAnalysis.Create(jobDescription, now);
        await _repository.AddAsync(analysis, ct);
        await _repository.SaveChangesAsync(ct);
        _cache.Set(AnalysisStatusDto.From(analysis));

        // --- Store the file; on failure fail the analysis so it never lingers as orphan Pending (Req 2.5) ---
        string reference;
        try
        {
            buffer.Position = 0;
            reference = await _resumeStore.SaveAsync(analysis.Id, buffer, extension, ct);
            analysis.AttachResume(reference, _time.GetUtcNow().UtcDateTime);
            await _repository.SaveChangesAsync(ct);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to store résumé for analysis {AnalysisId}", analysis.Id);
            analysis.MarkFailed("storage_failed", _time.GetUtcNow().UtcDateTime);
            await _repository.SaveChangesAsync(ct);
            var failedStatus = AnalysisStatusDto.From(analysis);
            _cache.Set(failedStatus);
            await _notifier.NotifyAsync(failedStatus, ct); // terminal → push (Req 10.4, 12.1)
            return SubmissionOutcome.Fail(SubmissionError.StorageFailure, "Could not store the uploaded file.");
        }

        // --- Dispatch to FastAPI: await only the 202 ack, never the analysis (Requirement 4, 5.4). ---
        var dispatchRequest = new AnalysisDispatchRequest(analysis.Id, reference, analysis.JobDescription, _webhook.PublicCallbackUrl);
        var dispatchOutcome = await _dispatcher.DispatchAsync(dispatchRequest, ct);
        var afterDispatch = _time.GetUtcNow().UtcDateTime;

        if (dispatchOutcome.Accepted)
        {
            analysis.MarkDispatched(afterDispatch);
            _logger.LogInformation("Dispatched analysis {AnalysisId}", analysis.Id);
        }
        else
        {
            // Dispatch failure never leaves the analysis stuck in Pending (Requirement 10.3, 10.5).
            analysis.MarkFailed(dispatchOutcome.FailureReason ?? "dispatch_failed", afterDispatch);
            _logger.LogWarning("Dispatch failed for analysis {AnalysisId}: {Reason}", analysis.Id, dispatchOutcome.FailureReason);
        }

        await _repository.SaveChangesAsync(ct);
        var finalStatus = AnalysisStatusDto.From(analysis);
        _cache.Set(finalStatus);
        if (!dispatchOutcome.Accepted)
            await _notifier.NotifyAsync(finalStatus, ct); // dispatch failure is terminal → push (Req 10.4, 12.1)

        // The client still receives 202 + id even on dispatch failure; the Failed outcome is
        // surfaced via status/push (Requirement 5.1, 10.4).
        return SubmissionOutcome.Ok(new AnalysisAccepted(analysis.Id, analysis.Status.ToString()));
    }

    /// <summary>
    /// Accepts a file only when the declared content type AND the content signature agree
    /// on PDF or DOCX (Requirement 1.2, 1.6). Returns the storage extension to use.
    /// </summary>
    private static bool TryResolveFileType(string contentType, byte[] bytes, out string extension)
    {
        extension = string.Empty;
        var declared = contentType?.Split(';')[0].Trim().ToLowerInvariant();

        if (declared == PdfContentType && StartsWith(bytes, PdfMagic))
        {
            extension = ".pdf";
            return true;
        }

        if (declared == DocxContentType && StartsWith(bytes, ZipMagic))
        {
            extension = ".docx";
            return true;
        }

        return false;
    }

    private static bool StartsWith(byte[] bytes, byte[] prefix)
    {
        if (bytes.Length < prefix.Length) return false;
        for (var i = 0; i < prefix.Length; i++)
            if (bytes[i] != prefix[i]) return false;
        return true;
    }
}
