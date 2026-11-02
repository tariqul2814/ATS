using System.ComponentModel.DataAnnotations;

namespace ATS_Web_API.Application.Options;

/// <summary>Webhook HMAC and callback settings (Requirement 7, 15). The secret comes from a secret store.</summary>
public sealed class WebhookOptions
{
    public const string SectionName = "Webhook";

    [Required, MinLength(16)]
    public string Secret { get; init; } = default!;

    /// <summary>Replay window: callbacks whose timestamp is outside this tolerance are rejected (Req 7, Q8).</summary>
    [Range(1, 3600)]
    public int ToleranceSeconds { get; init; } = 300;

    [Required, Url]
    public string PublicCallbackUrl { get; init; } = default!;
}
