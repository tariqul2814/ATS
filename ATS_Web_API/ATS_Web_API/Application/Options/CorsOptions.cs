using System.ComponentModel.DataAnnotations;

namespace ATS_Web_API.Application.Options;

/// <summary>Allowed browser origins for the Angular app (Requirement 15.4, 16.1).</summary>
public sealed class CorsOptions
{
    public const string SectionName = "Cors";

    [Required, MinLength(1)]
    public string[] AllowedOrigins { get; init; } = Array.Empty<string>();
}
