using System.Text.Json;
using ATS_Web_API.Application.Analyses;
using ATS_Web_API.Application.Dtos;

namespace ATS_Web_API.Endpoints;

public static class WebhookEndpoints
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    public static IEndpointRouteBuilder MapWebhookEndpoints(this IEndpointRouteBuilder app)
    {
        // POST /api/webhooks/analysis-completed — FastAPI posts the result (Requirement 6, 7, 8).
        app.MapPost("/api/webhooks/analysis-completed", async (
            HttpContext http,
            RecordAnalysisResultHandler handler,
            CancellationToken ct) =>
        {
            // The signature filter has already verified HMAC + timestamp and stashed the raw body.
            var body = http.Items[WebhookSignatureFilter.RawBodyItemKey] as byte[] ?? Array.Empty<byte>();

            AnalysisResultCallback? callback;
            try
            {
                callback = JsonSerializer.Deserialize<AnalysisResultCallback>(body, JsonOptions);
            }
            catch (JsonException)
            {
                return Results.BadRequest(new { error = "Malformed callback payload." });
            }

            var result = await handler.HandleAsync(callback, ct);
            return result switch
            {
                CallbackResult.Applied => Results.Ok(),
                CallbackResult.DuplicateIgnored => Results.Ok(),
                CallbackResult.NotFound => Results.NotFound(),
                _ => Results.BadRequest(new { error = "Invalid callback payload." })
            };
        })
        .AddEndpointFilter<WebhookSignatureFilter>()
        .DisableAntiforgery()
        .WithName("AnalysisCompletedWebhook")
        .WithTags("Webhooks");

        return app;
    }
}
