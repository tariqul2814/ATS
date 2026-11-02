using ATS_Web_API.Application.Abstractions;
using ATS_Web_API.Infrastructure.Persistence;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Xunit;

namespace ATS_Web_API.Tests.Integration;

/// <summary>
/// Hosts the real app for integration tests against a throwaway LocalDB database and a temp
/// storage folder. Config required by options validation is supplied in-memory so the host
/// starts deterministically regardless of user-secrets.
/// </summary>
public sealed class ApiFactory : WebApplicationFactory<Program>, IAsyncLifetime
{
    private readonly string _dbName = $"AtsApiTest_{Guid.NewGuid():N}";

    public string TempStorageRoot { get; } =
        Path.Combine(Path.GetTempPath(), "ats-api-tests", Guid.NewGuid().ToString("N"));

    public string WebhookSecret => "integration-test-secret-0123456789";

    /// <summary>The fake dispatcher used by the hosted app; tests can control its outcome.</summary>
    public TestAnalysisDispatcher Dispatcher { get; } = new();

    private string ConnectionString =>
        $"Server=(localdb)\\MSSQLLocalDB;Database={_dbName};Trusted_Connection=True;TrustServerCertificate=true";

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseEnvironment("Testing");

        builder.ConfigureAppConfiguration((_, cfg) =>
        {
            cfg.AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["ConnectionStrings:SqlServer"] = ConnectionString,
                ["Storage:Root"] = TempStorageRoot,
                ["Webhook:Secret"] = WebhookSecret,
                ["Webhook:PublicCallbackUrl"] = "https://localhost/api/webhooks/analysis-completed"
            });
        });

        builder.ConfigureServices(services =>
        {
            // Force the test connection regardless of registration-time config capture.
            var descriptor = services.SingleOrDefault(d => d.ServiceType == typeof(DbContextOptions<AppDbContext>));
            if (descriptor is not null) services.Remove(descriptor);
            services.AddDbContext<AppDbContext>(o => o.UseSqlServer(ConnectionString));

            // Replace the real FastAPI dispatcher with the controllable fake.
            services.RemoveAll<IAnalysisDispatcher>();
            services.AddSingleton<IAnalysisDispatcher>(Dispatcher);
        });
    }

    public async Task InitializeAsync()
    {
        using var scope = Services.CreateScope();
        await scope.ServiceProvider.GetRequiredService<AppDbContext>().Database.EnsureCreatedAsync();
    }

    async Task IAsyncLifetime.DisposeAsync()
    {
        using (var scope = Services.CreateScope())
            await scope.ServiceProvider.GetRequiredService<AppDbContext>().Database.EnsureDeletedAsync();

        if (Directory.Exists(TempStorageRoot))
            Directory.Delete(TempStorageRoot, recursive: true);

        await base.DisposeAsync();
    }
}
