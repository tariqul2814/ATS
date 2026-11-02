using System.Security.Cryptography;
using System.Text;
using ATS_Web_API.Application.Options;
using ATS_Web_API.Infrastructure.Security;
using FluentAssertions;
using Microsoft.Extensions.Options;
using Xunit;

namespace ATS_Web_API.Tests.Infrastructure;

public class HmacWebhookSignatureVerifierTests
{
    private const string Secret = "integration-test-secret-0123456789";
    private static readonly DateTimeOffset Now = new(2026, 10, 13, 12, 0, 0, TimeSpan.Zero);
    private static readonly byte[] Body = Encoding.UTF8.GetBytes("{\"analysisId\":\"abc\",\"status\":\"Completed\"}");

    private sealed class FixedTimeProvider : TimeProvider
    {
        private readonly DateTimeOffset _now;
        public FixedTimeProvider(DateTimeOffset now) => _now = now;
        public override DateTimeOffset GetUtcNow() => _now;
    }

    private static HmacWebhookSignatureVerifier Create(int tolerance = 300) =>
        new(Options.Create(new WebhookOptions { Secret = Secret, PublicCallbackUrl = "https://h/cb", ToleranceSeconds = tolerance }),
            new FixedTimeProvider(Now));

    private static string Sign(string secret, string timestamp, byte[] body)
    {
        var prefix = Encoding.ASCII.GetBytes(timestamp + ".");
        var message = prefix.Concat(body).ToArray();
        using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(secret));
        return Convert.ToHexString(hmac.ComputeHash(message)).ToLowerInvariant();
    }

    private static string Ts(DateTimeOffset t) => t.ToUnixTimeSeconds().ToString();

    [Fact]
    public void ValidSignature_Verifies()
    {
        var ts = Ts(Now);
        Create().Verify(Body, ts, Sign(Secret, ts, Body)).Should().BeTrue();
    }

    [Fact]
    public void ValidSignature_WithSha256Prefix_Verifies()
    {
        var ts = Ts(Now);
        Create().Verify(Body, ts, "sha256=" + Sign(Secret, ts, Body)).Should().BeTrue();
    }

    [Fact]
    public void MissingHeaders_Fail()
    {
        var ts = Ts(Now);
        Create().Verify(Body, null, Sign(Secret, ts, Body)).Should().BeFalse();
        Create().Verify(Body, ts, null).Should().BeFalse();
    }

    [Fact]
    public void WrongSecret_Fails()
    {
        var ts = Ts(Now);
        Create().Verify(Body, ts, Sign("the-wrong-secret-9876543210", ts, Body)).Should().BeFalse();
    }

    [Fact]
    public void TamperedBody_Fails()
    {
        var ts = Ts(Now);
        var signature = Sign(Secret, ts, Body);
        var tampered = Encoding.UTF8.GetBytes("{\"analysisId\":\"abc\",\"status\":\"Failed\"}");
        Create().Verify(tampered, ts, signature).Should().BeFalse();
    }

    [Fact]
    public void ExpiredTimestamp_Fails()
    {
        var old = Now.AddSeconds(-301); // just outside the 300s window
        Create().Verify(Body, Ts(old), Sign(Secret, Ts(old), Body)).Should().BeFalse();
    }

    [Fact]
    public void MalformedSignature_Fails()
    {
        var ts = Ts(Now);
        Create().Verify(Body, ts, "not-hex!!").Should().BeFalse();
    }
}
