using ATS_Web_API.Application.Abstractions;
using ATS_Web_API.Application.Options;
using Microsoft.Extensions.Options;

namespace ATS_Web_API.Infrastructure.Storage;

/// <summary>
/// Stores résumé files under the configured local folder as <c>{analysisId}{ext}</c> and returns
/// the full absolute path as the reference (Requirement 2). Swappable for FTP/SFTP/blob later (Req 2.7).
/// </summary>
public sealed class LocalFolderResumeStore : IResumeStore
{
    private readonly StorageOptions _options;

    public LocalFolderResumeStore(IOptions<StorageOptions> options) => _options = options.Value;

    public async Task<string> SaveAsync(Guid analysisId, Stream content, string fileExtension, CancellationToken ct)
    {
        Directory.CreateDirectory(_options.Root);

        var ext = fileExtension.StartsWith('.') ? fileExtension : "." + fileExtension;
        var key = $"{analysisId}{ext}";
        var fullPath = Path.Combine(_options.Root, key);

        await using var file = new FileStream(fullPath, FileMode.Create, FileAccess.Write, FileShare.None,
            bufferSize: 81920, useAsync: true);
        await content.CopyToAsync(file, ct);

        return fullPath;
    }
}
