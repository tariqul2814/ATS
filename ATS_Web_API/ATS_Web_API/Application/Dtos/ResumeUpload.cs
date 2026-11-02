namespace ATS_Web_API.Application.Dtos;

/// <summary>
/// Framework-agnostic view of an uploaded résumé passed from the endpoint to the application layer,
/// so the handler does not depend on ASP.NET types.
/// </summary>
public sealed record ResumeUpload(Stream Content, string FileName, string ContentType, long Length);
