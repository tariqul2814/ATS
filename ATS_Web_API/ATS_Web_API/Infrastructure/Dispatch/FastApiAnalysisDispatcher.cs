using System.Net;
using System.Net.Http.Json;
using ATS_Web_API.Application.Abstractions;
using ATS_Web_API.Application.Dtos;
using ATS_Web_API.Application.Options;
using Microsoft.Extensions.Options;

namespace ATS_Web_API.Infrastructure.Dispatch;

/// <summary>
/// Dispatches analyses to FastAPI over a typed HttpClient. Only HTTP 202 counts as accepted
/// (Requirement 4.2, 4.5); every other response or transport failure is a dispatch failure.
/// The retry policy for transient faults is configured on the HttpClient pipeline (Program.cs).
/// </summary>
public sealed class FastApiAnalysisDispatcher : IAnalysisDispatcher
{
    public const string DispatchTokenHeader = "X-Dispatch-Token";

    private readonly HttpClient _http;
    private readonly FastApiOptions _fastApi;
    private readonly ILogger<FastApiAnalysisDispatcher> _logger;

    public FastApiAnalysisDispatcher(HttpClient http, IOptions<FastApiOptions> fastApi, ILogger<FastApiAnalysisDispatcher> logger)
    {
        _http = http;
        _fastApi = fastApi.Value;
        _logger = logger;
    }

    public async Task<DispatchOutcome> DispatchAsync(AnalysisDispatchRequest request, CancellationToken ct)
    {
        try
        {
            using var message = new HttpRequestMessage(HttpMethod.Post, _fastApi.DispatchPath)
            {
                Content = JsonContent.Create(request) // web (camelCase) defaults, as PostAsJsonAsync used
            };
            if (!string.IsNullOrEmpty(_fastApi.DispatchToken))
                message.Headers.Add(DispatchTokenHeader, _fastApi.DispatchToken);

            using var response = await _http.SendAsync(message, ct);

            if (response.StatusCode == HttpStatusCode.Accepted)
                return DispatchOutcome.AcceptedResult();

            if (response.StatusCode == HttpStatusCode.Unauthorized)
                _logger.LogWarning(
                    "FastAPI rejected the dispatch token for analysis {AnalysisId}; FastApi:DispatchToken must " +
                    "equal the FastAPI service's APP_DISPATCH__TOKEN", request.AnalysisId);
            else
                _logger.LogWarning("FastAPI returned {Status} dispatching analysis {AnalysisId}",
                    (int)response.StatusCode, request.AnalysisId);
            return DispatchOutcome.Failed($"fastapi_status_{(int)response.StatusCode}");
        }
        catch (Exception ex) when (ex is not OperationCanceledException || !ct.IsCancellationRequested)
        {
            // Retries have already been exhausted by the resilience pipeline at this point.
            _logger.LogError(ex, "Dispatch to FastAPI failed for analysis {AnalysisId}", request.AnalysisId);
            return DispatchOutcome.Failed("dispatch_unreachable");
        }
    }
}
