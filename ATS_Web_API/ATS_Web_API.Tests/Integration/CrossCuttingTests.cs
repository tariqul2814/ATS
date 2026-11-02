using System.Net;
using FluentAssertions;
using Microsoft.AspNetCore.Hosting;
using Xunit;

namespace ATS_Web_API.Tests.Integration;

public class CrossCuttingTests : IClassFixture<ApiFactory>
{
    private readonly ApiFactory _factory;

    public CrossCuttingTests(ApiFactory factory) => _factory = factory;

    [Fact]
    public async Task Health_ReturnsHealthy()
    {
        var client = _factory.CreateClient();

        var response = await client.GetAsync("/health");

        response.StatusCode.Should().Be(HttpStatusCode.OK);
        (await response.Content.ReadAsStringAsync()).Should().Be("Healthy");
    }

    [Fact]
    public async Task Cors_AllowedOrigin_GetsAllowOriginHeader()
    {
        var client = _factory.CreateClient();
        var request = new HttpRequestMessage(HttpMethod.Get, "/health");
        request.Headers.Add("Origin", "http://localhost:4200");

        var response = await client.SendAsync(request);

        response.Headers.Contains("Access-Control-Allow-Origin").Should().BeTrue();
    }

    [Fact]
    public async Task Cors_DisallowedOrigin_HasNoAllowOriginHeader()
    {
        var client = _factory.CreateClient();
        var request = new HttpRequestMessage(HttpMethod.Get, "/health");
        request.Headers.Add("Origin", "http://evil.example");

        var response = await client.SendAsync(request);

        response.Headers.Contains("Access-Control-Allow-Origin").Should().BeFalse();
    }

    [Theory]
    [InlineData("http://127.0.0.1:4200")]
    [InlineData("http://localhost:4201")]
    [InlineData("http://[::1]:4200")]
    public async Task Cors_Development_AllowsAnyLoopbackOrigin(string origin)
    {
        var client = _factory.WithWebHostBuilder(b => b.UseEnvironment("Development")).CreateClient();
        var request = new HttpRequestMessage(HttpMethod.Get, "/health");
        request.Headers.Add("Origin", origin);

        var response = await client.SendAsync(request);

        response.Headers.GetValues("Access-Control-Allow-Origin").Should().ContainSingle().Which.Should().Be(origin);
    }

    [Theory]
    [InlineData("http://evil.example")]
    [InlineData("http://localhost.evil.example")]
    public async Task Cors_Development_RejectsNonLoopbackOrigin(string origin)
    {
        var client = _factory.WithWebHostBuilder(b => b.UseEnvironment("Development")).CreateClient();
        var request = new HttpRequestMessage(HttpMethod.Get, "/health");
        request.Headers.Add("Origin", origin);

        var response = await client.SendAsync(request);

        response.Headers.Contains("Access-Control-Allow-Origin").Should().BeFalse();
    }

    [Fact]
    public async Task Cors_OutsideDevelopment_RejectsUnlistedLoopbackOrigin()
    {
        var client = _factory.CreateClient();
        var request = new HttpRequestMessage(HttpMethod.Get, "/health");
        request.Headers.Add("Origin", "http://127.0.0.1:4200");

        var response = await client.SendAsync(request);

        response.Headers.Contains("Access-Control-Allow-Origin").Should().BeFalse();
    }
}
