using ATS_Web_API.Application.Abstractions;
using ATS_Web_API.Application.Dtos;

namespace ATS_Web_API.Tests.Integration;

/// <summary>
/// Controllable fake for the FastAPI dispatcher so integration tests never touch a real service.
/// Defaults to accepting (HTTP 202 equivalent); tests can flip <see cref="NextOutcome"/>.
/// </summary>
public sealed class TestAnalysisDispatcher : IAnalysisDispatcher
{
    public DispatchOutcome NextOutcome { get; set; } = DispatchOutcome.AcceptedResult();
    public List<AnalysisDispatchRequest> Requests { get; } = new();

    public Task<DispatchOutcome> DispatchAsync(AnalysisDispatchRequest request, CancellationToken ct)
    {
        Requests.Add(request);
        return Task.FromResult(NextOutcome);
    }
}
