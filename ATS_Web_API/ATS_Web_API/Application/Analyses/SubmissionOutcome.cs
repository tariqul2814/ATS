using ATS_Web_API.Application.Dtos;

namespace ATS_Web_API.Application.Analyses;

/// <summary>Classifies why a submission was rejected so the endpoint can map it to an HTTP status.</summary>
public enum SubmissionError
{
    None = 0,
    MissingFile,          // 400 (Req 1.4)
    TooManyFiles,         // 400 (Req 1.4)
    InvalidFileType,      // 400 (Req 1.2, 1.6)
    FileTooLarge,         // 413 (Req 1.5)
    EmptyJobDescription,  // 400 (Req 1.3)
    JobDescriptionTooLong,// 400 (Req 1 / Q3)
    StorageFailure        // 500 (Req 2.5)
}

/// <summary>Result of the StartResumeAnalysis use case.</summary>
public sealed record SubmissionOutcome(AnalysisAccepted? Accepted, SubmissionError Error, string? Message)
{
    public bool Succeeded => Error == SubmissionError.None;

    public static SubmissionOutcome Ok(AnalysisAccepted accepted) => new(accepted, SubmissionError.None, null);
    public static SubmissionOutcome Fail(SubmissionError error, string message) => new(null, error, message);
}
