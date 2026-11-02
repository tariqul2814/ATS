using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using ATS_Web_API.Application.Abstractions;
using ATS_Web_API.Application.Dtos;
using ATS_Web_API.Infrastructure.BackgroundServices;
using ATS_Web_API.Infrastructure.Persistence;
using FluentAssertions;
using Microsoft.AspNetCore.Http.Connections;
using Microsoft.AspNetCore.SignalR.Client;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Xunit;

namespace ATS_Web_API.Tests.Integration;

public class EndToEndTests : IClassFixture<ApiFactory>
{
    private readonly ApiFactory _factory;

    public EndToEndTests(ApiFactory factory) => _factory = factory;

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
    public async Task HappyPath_Submit_Dispatch_Webhook_Completes_And_Pushes()
    {
        _factory.Dispatcher.NextOutcome = DispatchOutcome.AcceptedResult();
        var client = _factory.CreateClient();

        var connection = new HubConnectionBuilder()
            .WithUrl("http://localhost/hubs/analysis", o =>
            {
                o.Transports = HttpTransportType.LongPolling;
                o.HttpMessageHandlerFactory = _ => _factory.Server.CreateHandler();
            })
            .Build();

        var pushed = new TaskCompletionSource<AnalysisStatusDto>(TaskCreationOptions.RunContinuationsAsynchronously);
        connection.On<AnalysisStatusDto>("analysisUpdated", dto => pushed.TrySetResult(dto));
        await connection.StartAsync();

        try
        {
            var id = await SubmitAsync(client);
            await connection.InvokeAsync("SubscribeToAnalysis", id);

            await CompleteAsync(client, id, new { score = 88 });

            var message = await pushed.Task.WaitAsync(TimeSpan.FromSeconds(10));
            message.AnalysisId.Should().Be(id);
            message.Status.Should().Be("Completed");

            // Status endpoint reflects the result.
            var status = await client.GetFromJsonAsync<AnalysisStatusDto>($"/api/analyses/{id}");
            status!.Status.Should().Be("Completed");
            status.ResultJson.Should().Contain("88");

            // History (per-GUID) reflects it too.
            var history = await client.GetFromJsonAsync<List<AnalysisHistoryItem>>($"/api/analyses?ids={id}");
            history.Should().ContainSingle(i => i.AnalysisId == id && i.HasResult);
        }
        finally
        {
            await connection.DisposeAsync();
        }
    }

    [Fact]
    public async Task DispatchFailure_SurfacesAsFailed()
    {
        _factory.Dispatcher.NextOutcome = DispatchOutcome.Failed("fastapi_status_500");
        var client = _factory.CreateClient();

        var id = await SubmitAsync(client);

        var status = await client.GetFromJsonAsync<AnalysisStatusDto>($"/api/analyses/{id}");
        status!.Status.Should().Be("Failed");

        _factory.Dispatcher.NextOutcome = DispatchOutcome.AcceptedResult(); // reset for other tests
    }

    [Fact]
    public async Task LostCallback_IsFailedByTheSweeper()
    {
        _factory.Dispatcher.NextOutcome = DispatchOutcome.AcceptedResult();
        var client = _factory.CreateClient();
        var id = await SubmitAsync(client);

        using var scope = _factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();

        // Backdate DispatchedAt so the analysis is past the dispatch timeout, simulating a lost callback.
        await db.Analyses.Where(a => a.Id == id)
            .ExecuteUpdateAsync(s => s.SetProperty(a => a.DispatchedAt, DateTime.UtcNow.AddMinutes(-30)));

        var sweep = scope.ServiceProvider.GetRequiredService<StalledAnalysisSweepService>();
        var failed = await sweep.SweepAsync(default);

        failed.Should().BeGreaterThanOrEqualTo(1);
        var status = await client.GetFromJsonAsync<AnalysisStatusDto>($"/api/analyses/{id}");
        status!.Status.Should().Be("Failed");
    }
}
