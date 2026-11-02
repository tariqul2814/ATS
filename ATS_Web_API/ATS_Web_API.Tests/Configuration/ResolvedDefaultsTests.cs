using ATS_Web_API.Application.Options;
using FluentAssertions;
using Xunit;

namespace ATS_Web_API.Tests.Configuration;

/// <summary>
/// Pins the resolved design defaults (Task 18.1) so a change is a deliberate decision, not a drift.
/// </summary>
public class ResolvedDefaultsTests
{
    [Fact]
    public void Uploads_Defaults_MatchResolvedDecisions()
    {
        var o = new UploadsOptions();
        o.MaxFileSizeBytes.Should().Be(5 * 1024 * 1024); // 5 MB (Q3)
        o.MaxJobDescriptionChars.Should().Be(20_000);     // (Q3)
    }

    [Fact]
    public void Dispatch_Defaults_MatchResolvedDecisions()
    {
        var o = new DispatchOptions();
        o.RetryCount.Should().Be(3);        // (Q4)
        o.BaseDelaySeconds.Should().Be(2);  // (Q4)
    }

    [Fact]
    public void Analysis_Defaults_MatchResolvedDecisions()
    {
        var o = new AnalysisOptions();
        o.DispatchTimeoutMinutes.Should().Be(10); // (Q5)
        o.SweepIntervalSeconds.Should().Be(60);   // (Q5)
    }

    [Fact]
    public void Webhook_ReplayWindow_MatchesResolvedDecision()
    {
        new WebhookOptions { Secret = "x", PublicCallbackUrl = "https://h/cb" }
            .ToleranceSeconds.Should().Be(300); // (Q8)
    }
}
