using ATS_Web_API.Application.Options;
using ATS_Web_API.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Extensions.Options;

namespace ATS_Web_API.Infrastructure.Health;

/// <summary>Readiness probe: SQL Server reachable and the storage folder writable (Requirement 18.5).</summary>
public sealed class ReadinessHealthCheck : IHealthCheck
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly StorageOptions _storage;

    public ReadinessHealthCheck(IServiceScopeFactory scopeFactory, IOptions<StorageOptions> storage)
    {
        _scopeFactory = scopeFactory;
        _storage = storage.Value;
    }

    public async Task<HealthCheckResult> CheckHealthAsync(HealthCheckContext context, CancellationToken ct = default)
    {
        using var scope = _scopeFactory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();

        if (!await db.Database.CanConnectAsync(ct))
            return HealthCheckResult.Unhealthy("Database is unreachable.");

        try
        {
            Directory.CreateDirectory(_storage.Root);
            var probe = Path.Combine(_storage.Root, ".health");
            await File.WriteAllTextAsync(probe, "ok", ct);
            File.Delete(probe);
        }
        catch (Exception ex)
        {
            return HealthCheckResult.Unhealthy("Storage folder is not writable.", ex);
        }

        return HealthCheckResult.Healthy();
    }
}
