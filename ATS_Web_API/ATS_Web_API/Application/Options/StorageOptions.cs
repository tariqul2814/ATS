using System.ComponentModel.DataAnnotations;

namespace ATS_Web_API.Application.Options;

/// <summary>Local résumé-storage settings (Requirement 2, 15). The folder is shared with FastAPI.</summary>
public sealed class StorageOptions
{
    public const string SectionName = "Storage";

    [Required]
    public string Root { get; init; } = default!;
}
