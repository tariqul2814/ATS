using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using ATS_Web_API.Application.Dtos;
using FluentAssertions;
using Xunit;

namespace ATS_Web_API.Tests.Integration;

public class StatusAndHistoryEndpointTests : IClassFixture<ApiFactory>
{
    private readonly ApiFactory _factory;

    public StatusAndHistoryEndpointTests(ApiFactory factory) => _factory = factory;

    private static readonly byte[] PdfBytes = { 0x25, 0x50, 0x44, 0x46, 0x2D, 0x31, 0x2E, 0x34 };

    private async Task<Guid> SubmitAsync(HttpClient client)
    {
        var form = new MultipartFormDataContent();
        var file = new ByteArrayContent(PdfBytes);
        file.Headers.ContentType = new MediaTypeHeaderValue("application/pdf");
        form.Add(file, "files", "cv.pdf");
        form.Add(new StringContent("Senior .NET engineer"), "jobDescription");
        var response = await client.PostAsync("/api/analyses", form);
        var body = await response.Content.ReadFromJsonAsync<AnalysisAccepted>();
        return body!.AnalysisId;
    }

    private async Task CompleteAsync(HttpClient client, Guid id, object result)
    {
        var payload = JsonSerializer.Serialize(new { analysisId = id, status = "Completed", result, error = (string?)null });
        var bytes = Encoding.UTF8.GetBytes(payload);
        var ts = DateTimeOffset.UtcNow.ToUnixTimeSeconds().ToString();
        var prefix = Encoding.ASCII.GetBytes(ts + ".");
        using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(_factory.WebhookSecret));
        var sig = Convert.ToHexString(hmac.ComputeHash(prefix.Concat(bytes).ToArray())).ToLowerInvariant();

        var req = new HttpRequestMessage(HttpMethod.Post, "/api/webhooks/analysis-completed")
        {
            Content = new ByteArrayContent(bytes)
        };
        req.Content.Headers.ContentType = new MediaTypeHeaderValue("application/json");
        req.Headers.Add("X-Timestamp", ts);
        req.Headers.Add("X-Signature", sig);
        (await client.SendAsync(req)).EnsureSuccessStatusCode();
    }

    [Fact]
    public async Task GetStatus_ReturnsCurrentStatus()
    {
        var client = _factory.CreateClient();
        var id = await SubmitAsync(client);

        var dto = await client.GetFromJsonAsync<AnalysisStatusDto>($"/api/analyses/{id}");

        dto!.AnalysisId.Should().Be(id);
        dto.Status.Should().Be("Dispatched");
    }

    [Fact]
    public async Task GetStatus_Unknown_Returns404()
    {
        var client = _factory.CreateClient();
        var response = await client.GetAsync($"/api/analyses/{Guid.NewGuid()}");
        response.StatusCode.Should().Be(HttpStatusCode.NotFound);
    }

    [Fact]
    public async Task GetResult_BeforeCompletion_Returns409()
    {
        var client = _factory.CreateClient();
        var id = await SubmitAsync(client);

        var response = await client.GetAsync($"/api/analyses/{id}/result");

        response.StatusCode.Should().Be(HttpStatusCode.Conflict);
    }

    [Fact]
    public async Task GetResult_AfterCompletion_ReturnsJsonDocument()
    {
        var client = _factory.CreateClient();
        var id = await SubmitAsync(client);
        await CompleteAsync(client, id, new { score = 77 });

        var response = await client.GetAsync($"/api/analyses/{id}/result");

        response.StatusCode.Should().Be(HttpStatusCode.OK);
        (await response.Content.ReadAsStringAsync()).Should().Contain("77");
    }

    [Fact]
    public async Task History_ByIds_ReturnsRequestedAnalyses()
    {
        var client = _factory.CreateClient();
        var id = await SubmitAsync(client);

        var items = await client.GetFromJsonAsync<List<AnalysisHistoryItem>>($"/api/analyses?ids={id}");

        items.Should().ContainSingle(i => i.AnalysisId == id);
    }

    [Fact]
    public async Task History_NoIds_ReturnsEmpty_NoListAll()
    {
        var client = _factory.CreateClient();
        await SubmitAsync(client); // ensure at least one analysis exists

        var items = await client.GetFromJsonAsync<List<AnalysisHistoryItem>>("/api/analyses");

        items.Should().BeEmpty();
    }
}
