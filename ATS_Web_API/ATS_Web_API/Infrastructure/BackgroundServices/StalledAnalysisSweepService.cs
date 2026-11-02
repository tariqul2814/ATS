using ATS_Web_API.Application;
using ATS_Web_API.Application.Abstractions;
using ATS_Web_API.Application.Dtos;
using ATS_Web_API.Application.Options;
using ATS_Web_API.Domain.Exceptions;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace ATS_Web_API.Infrastructure.BackgroundServices;

/// <summary>
/// One sweep pass: fails analyses stuck in Dispatched past the configured timeout, applying the
/// same guarded transition and concurrency rules as the webhook (Requirement 11).
/// </summary>
public sealed class StalledAnalysisSweepService
{
    private readonly IAnalysisRepository _repository;
    private readonly IAnalysisStatusCache _cache;
    private readonly IAnalysisNotifier _notifier;
    private readonly AnalysisOptions _options;
    private readonly TimeProvider _time;
    private readonly ILogger<StalledAnalysisSweepService> _logger;

    public StalledAnalysisSweepService(
        IAnalysisRepository repository,
        IAnalysisStatusCache cache,
        IAnalysisNotifier notifier,
        IOptions<AnalysisOptions> options,
        TimeProvider time,
        ILogger<StalledAnalysisSweepService> logger)
    {
        _repository = repository;
        _cache = cache;
        _notifier = notifier;
        _options = options.Value;
        _time = time;
        _logger = logger;
    }

    /// <summary>Returns the number of analyses failed this pass.</summary>
    public async Task<int> SweepAsync(CancellationToken ct)
    {
        var cutoff = _time.GetUtcNow().UtcDateTime - TimeSpan.FromMinutes(_options.DispatchTimeoutMinutes);
        var stalled = await _repository.GetStalledDispatchedAsync(cutoff, ct);

        var failed = 0;
        foreach (var analysis in stalled)
        {
            try
            {
                analysis.MarkFailed("dispatch_timeout", _time.GetUtcNow().UtcDateTime);
                await _repository.SaveChangesAsync(ct);

                var status = AnalysisStatusDto.From(analysis);
                _cache.Set(status);
                await _notifier.NotifyAsync(status, ct);
                failed++;
            }
            catch (ConcurrencyConflictException)
            {
                // A callback transitioned it first; its terminal state stands (Req 11.3, 11.4).
                _logger.LogInformation("Analysis {AnalysisId} changed during sweep; skipping.", analysis.Id);
            }
            catch (InvalidAnalysisTransitionException)
            {
                _logger.LogInformation("Analysis {AnalysisId} no longer in a failable state; skipping.", analysis.Id);
            }
        }

        return failed;
    }
}
