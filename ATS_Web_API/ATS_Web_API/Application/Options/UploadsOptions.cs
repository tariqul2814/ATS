using System.ComponentModel.DataAnnotations;

namespace ATS_Web_API.Application.Options;

/// <summary>Upload constraints for submissions (Requirement 1.5, 15, Q3).</summary>
public sealed class UploadsOptions
{
    public const string SectionName = "Uploads";

    [Range(1, 104_857_600)] // up to 100 MB hard ceiling; default 5 MB
    public long MaxFileSizeBytes { get; init; } = 5 * 1024 * 1024;

    [Range(1, 200_000)]
    public int MaxJobDescriptionChars { get; init; } = 20_000;
}
