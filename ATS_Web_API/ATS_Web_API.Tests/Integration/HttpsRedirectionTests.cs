using System.Net;
using FluentAssertions;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Xunit;

namespace ATS_Web_API.Tests.Integration;

/// <summary>
/// The FastAPI webhook must be reachable over plain HTTP (a signed server-to-server POST cannot
/// follow a redirect), while the rest of the API still redirects to HTTPS.
/// </summary>
public class HttpsRedirectionTests : IClassFixture<ApiFactory>
{
    private readonly ApiFactory _factory;

    public HttpsRedirectionTests(ApiFactory factory) => _factory = factory;

    private HttpClient CreateClientWithHttpsPort() =>
        _factory
            .WithWebHostBuilder(b => b.UseSetting("https_port", "7120"))
            .CreateClient(new WebApplicationFactoryClientOptions { AllowAutoRedirect = false });

    [Fact]
    public async Task ApiRoutes_OverHttp_RedirectToHttps()
    {
        var client = CreateClientWithHttpsPort();

        var response = await client.GetAsync($"/api/analyses/{Guid.NewGuid()}");

        response.StatusCode.Should().Be(HttpStatusCode.TemporaryRedirect);
        response.Headers.Location!.Scheme.Should().Be("https");
    }

    [Fact]
    public async Task Webhook_OverHttp_IsNotRedirected()
    {
        var client = CreateClientWithHttpsPort();

        var response = await client.PostAsync("/api/webhooks/analysis-completed",
            new StringContent("{}", System.Text.Encoding.UTF8, "application/json"));

        // Reaches the signature filter (unsigned -> 401) instead of being bounced to HTTPS.
        response.StatusCode.Should().Be(HttpStatusCode.Unauthorized);
    }
}
