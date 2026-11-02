using System.ComponentModel.DataAnnotations;

namespace ATS_Web_API.Application.Options;

/// <summary>Settings for dispatching analyses to the external FastAPI service (Requirement 4, 15).</summary>
public sealed class FastApiOptions
{
    public const string SectionName = "FastApi";

    [Required, Url]
    public string BaseUrl { get; init; } = default!;

    [Required]
    public string DispatchPath { get; init; } = "/analyze";

    [Range(1, 300)]
    public int DispatchHttpTimeoutSeconds { get; init; } = 10;

    /// <summary>
    /// Shared token sent as <c>X-Dispatch-Token</c> on every dispatch; must equal the FastAPI service's
    /// <c>APP_DISPATCH__TOKEN</c>. Optional: when unset, no header is sent. Keep it in a secret store
    /// (user-secrets in development), never in appsettings.json.
    /// </summary>
    [MinLength(16)]
    public string? DispatchToken { get; init; }
}
