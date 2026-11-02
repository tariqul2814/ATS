using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;
using Microsoft.Extensions.Configuration;

namespace ATS_Web_API.Infrastructure.Persistence;

/// <summary>
/// Design-time factory so `dotnet ef migrations`/`database update` can construct the context
/// without executing the web host (avoids running the app or triggering options validation).
/// </summary>
public sealed class AppDbContextFactory : IDesignTimeDbContextFactory<AppDbContext>
{
    public AppDbContext CreateDbContext(string[] args)
    {
        var configuration = new ConfigurationBuilder()
            .SetBasePath(Directory.GetCurrentDirectory())
            .AddJsonFile("appsettings.json", optional: false)
            .AddJsonFile("appsettings.Development.json", optional: true)
            .Build();

        var options = new DbContextOptionsBuilder<AppDbContext>()
            .UseSqlServer(configuration.GetConnectionString("SqlServer"))
            .Options;

        return new AppDbContext(options);
    }
}
