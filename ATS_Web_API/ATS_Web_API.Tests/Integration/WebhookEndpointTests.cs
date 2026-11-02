using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using ATS_Web_API.Application.Dtos;
using ATS_Web_API.Domain.Enums;
using ATS_Web_API.Infrastructure.Persistence;
using FluentAssertions;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Xunit;

namespace ATS_Web_API.Tests.Integration;

public class WebhookEndpointTests : IClassFixture<ApiFactory>
{
    private readonly ApiFactory _factory;

    public WebhookEndpointTests(ApiFactory factory) => _factory = factory;

    private static readonly byte[] PdfBytes = { 0x25, 0x50, 0x44, 0x46, 0x2D, 0x31, 0x2E, 0x34 };

    private async Task<Guid> SubmitAsync(HttpClient client)
    {
        var form = new MultipartFormDataContent();
        var file = new ByteArrayContent(PdfBytes);
        file.Headers.ContentType = new MediaTypeHeaderValue("application/pdf");
        form.Add(file, "files", "cv.pdf");
        form.Add(new StringContent("Senior .NET engineer"), "jobDescription");

        var response = await client.PostAsync("/api/analyses", form);
        response.StatusCode.Should().Be(HttpStatusCode.Accepted);
        var body = await response.Content.ReadFromJsonAsync<AnalysisAccepted>();
        return body!.AnalysisId;
    }

    private HttpRequestMessage BuildCallback(Guid id, string status, object? result, string? error, bool sign = true)
    {
        var payload = JsonSerializer.Serialize(new { analysisId = id, status, result, error });
        var body = Encoding.UTF8.GetBytes(payload);

        var request = new HttpRequestMessage(HttpMethod.Post, "/api/webhooks/analysis-completed")
        {
            Content = new ByteArrayContent(body)
        };
        request.Content.Headers.ContentType = new MediaTypeHeaderValue("application/json");

        if (sign)
        {
            var ts = DateTimeOffset.UtcNow.ToUnixTimeSeconds().ToString();
            request.Headers.Add("X-Timestamp", ts);
            request.Headers.Add("X-Signature", Sign(_factory.WebhookSecret, ts, body));
        }

        return request;
    }

    private static string Sign(string secret, string timestamp, byte[] body)
    {
        var prefix = Encoding.ASCII.GetBytes(timestamp + ".");
        var message = prefix.Concat(body).ToArray();
        using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(secret));
        return Convert.ToHexString(hmac.ComputeHash(message)).ToLowerInvariant();
    }

    [Fact]
    public async Task SignedCompletedCallback_Returns200_AndMarksCompleted()
    {
        var client = _factory.CreateClient();
        var id = await SubmitAsync(client);

        var response = await client.SendAsync(
            BuildCallback(id, "Completed", new { score = 82 }, null));

        response.StatusCode.Should().Be(HttpStatusCode.OK);

        using var scope = _factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
        var analysis = await db.Analyses.AsNoTracking().FirstAsync(a => a.Id == id);
        analysis.Status.Should().Be(AnalysisStatus.Completed);
        analysis.ResultJson.Should().Contain("82");
    }

    [Fact]
    public async Task UnsignedCallback_Returns401()
    {
        var client = _factory.CreateClient();
        var id = await SubmitAsync(client);

        var response = await client.SendAsync(
            BuildCallback(id, "Completed", new { score = 1 }, null, sign: false));

        response.StatusCode.Should().Be(HttpStatusCode.Unauthorized);
    }

    [Fact]
    public async Task SignedCallback_ForUnknownId_Returns404()
    {
        var client = _factory.CreateClient();

        var response = await client.SendAsync(
            BuildCallback(Guid.NewGuid(), "Completed", new { score = 1 }, null));

        response.StatusCode.Should().Be(HttpStatusCode.NotFound);
    }
}
