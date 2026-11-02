using ATS_Web_API.Application.Abstractions;
using ATS_Web_API.Application.Dtos;
using ATS_Web_API.Domain.Enums;
using ATS_Web_API.Domain.Exceptions;
using Microsoft.Extensions.Logging;

namespace ATS_Web_API.Application.Analyses;

/// <summary>How the endpoint should respond to a callback.</summary>
public enum CallbackResult
{
    Applied,          // 200 — result recorded
    DuplicateIgnored, // 200 — already terminal / race loser, no change (Req 8)
    NotFound,         // 404 — unknown analysis id (Req 6.5)
    Invalid           // 400 — malformed/missing fields (Req 6.6)
}

/// <summary>
/// Applies a FastAPI result callback to an analysis, with idempotency and the webhook-vs-sweeper
/// concurrency guard (Requirement 6, 8, 9.6).
/// </summary>
public class RecordAnalysisResultHandler
{
    private const string Completed = "Completed";
    private const string Failed = "Failed";

    private readonly IAnalysisRepository _repository;
    private readonly IAnalysisStatusCache _cache;
    private readonly IAnalysisNotifier _notifier;
    private readonly TimeProvider _time;
    private readonly ILogger<RecordAnalysisResultHandler> _logger;

    public RecordAnalysisResultHandler(
        IAnalysisRepository repository,
        IAnalysisStatusCache cache,
        IAnalysisNotifier notifier,
        TimeProvider time,
        ILogger<RecordAnalysisResultHandler> logger)
    {
        _repository = repository;
        _cache = cache;
        _notifier = notifier;
        _time = time;
        _logger = logger;
    }

    public virtual async Task<CallbackResult> HandleAsync(AnalysisResultCallback? callback, CancellationToken ct)
    {
        // --- Envelope validation (Requirement 6.6) ---
        if (callback is null || callback.AnalysisId == Guid.Empty || string.IsNullOrWhiteSpace(callback.Status))
            return CallbackResult.Invalid;

        var completed = string.Equals(callback.Status, Completed, StringComparison.OrdinalIgnoreCase);
        var failed = string.Equals(callback.Status, Failed, StringComparison.OrdinalIgnoreCase);
        if (!completed && !failed)
            return CallbackResult.Invalid;

        if (completed && callback.Result is null)
            return CallbackResult.Invalid; // result required when Completed

        var analysis = await _repository.GetAsync(callback.AnalysisId, ct);
        if (analysis is null)
            return CallbackResult.NotFound;

        // --- Idempotency: already terminal → no change (Requirement 8.1, 8.2) ---
        if (analysis.Status is AnalysisStatus.Completed or AnalysisStatus.Failed)
        {
            _logger.LogInformation("Duplicate callback for terminal analysis {AnalysisId}; ignoring.", analysis.Id);
            return CallbackResult.DuplicateIgnored;
        }

        try
        {
            var now = _time.GetUtcNow().UtcDateTime;
            if (completed)
                analysis.MarkCompleted(callback.Result!.Value.GetRawText(), now);
            else
                analysis.MarkFailed(string.IsNullOrWhiteSpace(callback.Error) ? "analysis_failed" : callback.Error!, now);

            await _repository.SaveChangesAsync(ct);
            var status = AnalysisStatusDto.From(analysis);
            _cache.Set(status);
            await _notifier.NotifyAsync(status, ct); // terminal → push (Req 12.1)
            _logger.LogInformation("Recorded {Status} for analysis {AnalysisId}", analysis.Status, analysis.Id);
            return CallbackResult.Applied;
        }
        catch (ConcurrencyConflictException)
        {
            // The sweeper (or another delivery) transitioned this analysis first; its terminal
            // state stands and we treat this as an idempotent no-op (Requirement 8.3, 8.4, 11.4).
            _logger.LogInformation("Concurrency conflict applying callback for {AnalysisId}; treating as duplicate.", analysis.Id);
            return CallbackResult.DuplicateIgnored;
        }
        catch (InvalidAnalysisTransitionException)
        {
            // Callback does not fit the current (non-terminal) state.
            return CallbackResult.Invalid;
        }
    }
}
