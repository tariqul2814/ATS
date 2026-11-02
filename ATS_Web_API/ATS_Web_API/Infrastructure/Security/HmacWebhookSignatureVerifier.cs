using System.Security.Cryptography;
using System.Text;
using ATS_Web_API.Application.Abstractions;
using ATS_Web_API.Application.Options;
using Microsoft.Extensions.Options;

namespace ATS_Web_API.Infrastructure.Security;

/// <summary>
/// HMAC-SHA256 verification over <c>{timestamp}.{rawBody}</c> with the shared webhook secret,
/// a constant-time comparison, and a replay window (Requirement 7, resolved Q8).
/// </summary>
public sealed class HmacWebhookSignatureVerifier : IWebhookSignatureVerifier
{
    private readonly WebhookOptions _options;
    private readonly TimeProvider _time;

    public HmacWebhookSignatureVerifier(IOptions<WebhookOptions> options, TimeProvider time)
    {
        _options = options.Value;
        _time = time;
    }

    public bool Verify(byte[] rawBody, string? timestampHeader, string? signatureHeader)
    {
        if (string.IsNullOrWhiteSpace(timestampHeader) || string.IsNullOrWhiteSpace(signatureHeader))
            return false;

        if (!long.TryParse(timestampHeader, out var unixSeconds))
            return false;

        // Replay window (Req 7, Q8).
        var timestamp = DateTimeOffset.FromUnixTimeSeconds(unixSeconds);
        if (Math.Abs((_time.GetUtcNow() - timestamp).TotalSeconds) > _options.ToleranceSeconds)
            return false;

        if (!TryParseSignature(signatureHeader, out var provided))
            return false;

        var computed = ComputeHmac(timestampHeader, rawBody);
        return CryptographicOperations.FixedTimeEquals(provided, computed);
    }

    private byte[] ComputeHmac(string timestamp, byte[] rawBody)
    {
        var prefix = Encoding.ASCII.GetBytes(timestamp + ".");
        var message = new byte[prefix.Length + rawBody.Length];
        Buffer.BlockCopy(prefix, 0, message, 0, prefix.Length);
        Buffer.BlockCopy(rawBody, 0, message, prefix.Length, rawBody.Length);

        using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(_options.Secret));
        return hmac.ComputeHash(message);
    }

    private static bool TryParseSignature(string header, out byte[] signature)
    {
        signature = Array.Empty<byte>();
        var hex = header.StartsWith("sha256=", StringComparison.OrdinalIgnoreCase)
            ? header["sha256=".Length..]
            : header;

        try
        {
            signature = Convert.FromHexString(hex);
            return true;
        }
        catch (FormatException)
        {
            return false;
        }
    }
}
