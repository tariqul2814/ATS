namespace ATS_Web_API.Application.Abstractions;

/// <summary>Verifies the HMAC signature and timestamp of an incoming webhook callback (Requirement 7).</summary>
public interface IWebhookSignatureVerifier
{
    bool Verify(byte[] rawBody, string? timestampHeader, string? signatureHeader);
}
