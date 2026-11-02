using ATS_Web_API.Application.Abstractions;

namespace ATS_Web_API.Endpoints;

/// <summary>
/// Endpoint filter that reads the raw webhook body, verifies the HMAC signature + timestamp
/// BEFORE any deserialization or state logic, and short-circuits with 401 on failure (Req 7.2, 7.6).
/// The verified raw body is stashed for the handler so it is read only once.
/// </summary>
public sealed class WebhookSignatureFilter : IEndpointFilter
{
    public const string RawBodyItemKey = "webhook-raw-body";

    private readonly IWebhookSignatureVerifier _verifier;

    public WebhookSignatureFilter(IWebhookSignatureVerifier verifier) => _verifier = verifier;

    public async ValueTask<object?> InvokeAsync(EndpointFilterInvocationContext context, EndpointFilterDelegate next)
    {
        var http = context.HttpContext;

        byte[] body;
        using (var ms = new MemoryStream())
        {
            await http.Request.Body.CopyToAsync(ms, http.RequestAborted);
            body = ms.ToArray();
        }

        var timestamp = http.Request.Headers["X-Timestamp"].FirstOrDefault();
        var signature = http.Request.Headers["X-Signature"].FirstOrDefault();

        if (!_verifier.Verify(body, timestamp, signature))
            return Results.Unauthorized();

        http.Items[RawBodyItemKey] = body;
        return await next(context);
    }
}
