namespace ATS_Web_API.Application.Abstractions;

/// <summary>
/// Storage port for résumé files (Requirement 2). Implementations persist the file to a shared
/// location and return the full path to it, which is stored and handed to FastAPI (Req 2.2, 2.4, 2.7).
/// </summary>
public interface IResumeStore
{
    Task<string> SaveAsync(Guid analysisId, Stream content, string fileExtension, CancellationToken ct);
}
