using System.Net;
using ATS_Web_API.Application.Dtos;
using ATS_Web_API.Application.Options;
using ATS_Web_API.Infrastructure.Dispatch;
using FluentAssertions;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using Xunit;

namespace ATS_Web_API.Tests.Infrastructure;

public class FastApiAnalysisDispatcherTests
{
    private sealed class StubHandler : HttpMessageHandler
    {
        private readonly Func<HttpRequestMessage, HttpResponseMessage> _responder;
        public StubHandler(Func<HttpRequestMessage, HttpResponseMessage> responder) => _responder = responder;

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
            => Task.FromResult(_responder(request));
    }

    private static FastApiAnalysisDispatcher Create(HttpMessageHandler handler, string? token = null) =>
        new(new HttpClient(handler) { BaseAddress = new Uri("http://fastapi.local") },
            Options.Create(new FastApiOptions
            {
                BaseUrl = "http://fastapi.local", DispatchPath = "/analyze", DispatchToken = token
            }),
            NullLogger<FastApiAnalysisDispatcher>.Instance);

    private static AnalysisDispatchRequest Request() =>
        new(Guid.NewGuid(), "x.pdf", "jd", "https://host/cb");

    [Fact]
    public async Task Http202_IsAccepted()
    {
        var dispatcher = Create(new StubHandler(_ => new HttpResponseMessage(HttpStatusCode.Accepted)));

        var outcome = await dispatcher.DispatchAsync(Request(), default);

        outcome.Accepted.Should().BeTrue();
    }

    [Fact]
    public async Task Non202Response_IsFailed()
    {
        var dispatcher = Create(new StubHandler(_ => new HttpResponseMessage(HttpStatusCode.InternalServerError)));

        var outcome = await dispatcher.DispatchAsync(Request(), default);

        outcome.Accepted.Should().BeFalse();
        outcome.FailureReason.Should().Be("fastapi_status_500");
    }

    [Fact]
    public async Task ConfiguredToken_IsSentAsHeader()
    {
        HttpRequestMessage? sent = null;
        var dispatcher = Create(new StubHandler(r => { sent = r; return new HttpResponseMessage(HttpStatusCode.Accepted); }),
            token: "dispatch-token-0123456789");

        await dispatcher.DispatchAsync(Request(), default);

        sent!.Headers.GetValues(FastApiAnalysisDispatcher.DispatchTokenHeader)
            .Should().ContainSingle().Which.Should().Be("dispatch-token-0123456789");
    }

    [Fact]
    public async Task NoToken_SendsNoHeader()
    {
        HttpRequestMessage? sent = null;
        var dispatcher = Create(new StubHandler(r => { sent = r; return new HttpResponseMessage(HttpStatusCode.Accepted); }));

        await dispatcher.DispatchAsync(Request(), default);

        sent!.Headers.Contains(FastApiAnalysisDispatcher.DispatchTokenHeader).Should().BeFalse();
    }

    [Fact]
    public async Task Body_IsCamelCaseJson_AtTheDispatchPath()
    {
        string? body = null;
        HttpRequestMessage? sent = null;
        var dispatcher = Create(new StubHandler(r =>
        {
            sent = r;
            body = r.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
            return new HttpResponseMessage(HttpStatusCode.Accepted);
        }));
        var request = Request();

        await dispatcher.DispatchAsync(request, default);

        sent!.Method.Should().Be(HttpMethod.Post);
        sent.RequestUri!.AbsolutePath.Should().Be("/analyze");
        sent.Content!.Headers.ContentType!.MediaType.Should().Be("application/json");
        body.Should().Contain($"\"analysisId\":\"{request.AnalysisId}\"")
            .And.Contain("\"resumeFileReference\":\"x.pdf\"")
            .And.Contain("\"jobDescription\":\"jd\"")
            .And.Contain("\"callbackUrl\":\"https://host/cb\"");
    }

    [Fact]
    public async Task RejectedToken_IsFailed()
    {
        var dispatcher = Create(new StubHandler(_ => new HttpResponseMessage(HttpStatusCode.Unauthorized)),
            token: "wrong-token-0123456789");

        var outcome = await dispatcher.DispatchAsync(Request(), default);

        outcome.Accepted.Should().BeFalse();
        outcome.FailureReason.Should().Be("fastapi_status_401");
    }

    [Fact]
    public async Task TransportException_IsFailed()
    {
        var dispatcher = Create(new StubHandler(_ => throw new HttpRequestException("connection refused")));

        var outcome = await dispatcher.DispatchAsync(Request(), default);

        outcome.Accepted.Should().BeFalse();
        outcome.FailureReason.Should().Be("dispatch_unreachable");
    }
}
