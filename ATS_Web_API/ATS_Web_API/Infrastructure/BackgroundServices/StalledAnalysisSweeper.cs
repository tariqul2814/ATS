using ATS_Web_API.Application.Options;
using Microsoft.Extensions.Options;

namespace ATS_Web_API.Infrastructure.BackgroundServices;

/// <summary>
/// Hosted service that runs <see cref="StalledAnalysisSweepService"/> on the configured interval.
/// A failing tick is logged and the loop continues on schedule (Requirement 11.7).
/// </summary>
public sealed class StalledAnalysisSweeper : BackgroundService
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly AnalysisOptions _options;
    private readonly ILogger<StalledAnalysisSweeper> _logger;

    public StalledAnalysisSweeper(
        IServiceScopeFactory scopeFactory,
        IOptions<AnalysisOptions> options,
        ILogger<StalledAnalysisSweeper> logger)
    {
        _scopeFactory = scopeFactory;
        _options = options.Value;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(_options.SweepIntervalSeconds));

        while (!stoppingToken.IsCancellationRequested && await timer.WaitForNextTickAsync(stoppingToken))
        {
            try
            {
                using var scope = _scopeFactory.CreateScope();
                var sweep = scope.ServiceProvider.GetRequiredService<StalledAnalysisSweepService>();
                var count = await sweep.SweepAsync(stoppingToken);
                if (count > 0)
                    _logger.LogInformation("Sweeper failed {Count} stalled analyses.", count);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Sweep tick failed; continuing on schedule.");
            }
        }
    }
}
