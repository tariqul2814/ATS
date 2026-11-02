using ATS_Web_API.Domain.Enums;
using ATS_Web_API.Domain.Exceptions;

namespace ATS_Web_API.Domain.Entities;

/// <summary>
/// The tracked unit of work: one résumé analysed against one job description (Requirement 3).
/// All lifecycle changes go through the guarded transition methods so the aggregate can never
/// reach an invalid state (Requirement 9).
/// </summary>
public class ResumeAnalysis
{
    public Guid Id { get; private set; }
    public AnalysisStatus Status { get; private set; }

    /// <summary>Opaque relative storage key; null until the résumé file has been stored.</summary>
    public string? ResumeFileReference { get; private set; }

    public string JobDescription { get; private set; }

    /// <summary>The analysis result as a single JSON document; null until Completed (Requirement 3.5).</summary>
    public string? ResultJson { get; private set; }

    /// <summary>Failure reason; set when the analysis transitions to Failed.</summary>
    public string? Error { get; private set; }

    public DateTime CreatedAt { get; private set; }
    public DateTime UpdatedAt { get; private set; }
    public DateTime? DispatchedAt { get; private set; }
    public DateTime? CompletedAt { get; private set; }

    /// <summary>Optimistic-concurrency token enforced by SQL Server rowversion (Requirement 9.6).</summary>
    public byte[] RowVersion { get; private set; } = Array.Empty<byte>();

    // Parameterless constructor for EF Core materialization.
    private ResumeAnalysis()
    {
        JobDescription = null!;
    }

    private ResumeAnalysis(Guid id, string jobDescription, DateTime utcNow)
    {
        Id = id;
        JobDescription = jobDescription;
        Status = AnalysisStatus.Pending;
        CreatedAt = utcNow;
        UpdatedAt = utcNow;
    }

    /// <summary>
    /// Creates a new analysis in <see cref="AnalysisStatus.Pending"/> with a generated GUID id
    /// (Requirement 3.1, 3.3). The id is available immediately so the résumé file can be stored
    /// under it before <see cref="AttachResume"/> is called.
    /// </summary>
    public static ResumeAnalysis Create(string jobDescription, DateTime utcNow)
    {
        if (string.IsNullOrWhiteSpace(jobDescription))
            throw new ArgumentException("Job description must not be empty.", nameof(jobDescription));

        return new ResumeAnalysis(Guid.NewGuid(), jobDescription, utcNow);
    }

    /// <summary>
    /// Records the stored résumé file reference. Valid only while the analysis is still
    /// <see cref="AnalysisStatus.Pending"/> (i.e., before dispatch) — Requirement 2.2.
    /// </summary>
    public void AttachResume(string fileReference, DateTime utcNow)
    {
        if (string.IsNullOrWhiteSpace(fileReference))
            throw new ArgumentException("File reference must not be empty.", nameof(fileReference));
        if (Status != AnalysisStatus.Pending)
            throw new InvalidAnalysisTransitionException(Status, "attach résumé");

        ResumeFileReference = fileReference;
        UpdatedAt = utcNow;
    }

    /// <summary>Pending → Dispatched, after FastAPI acknowledges with 202 (Requirement 4.2).</summary>
    public void MarkDispatched(DateTime utcNow)
    {
        if (Status != AnalysisStatus.Pending)
            throw new InvalidAnalysisTransitionException(Status, "dispatch");

        Status = AnalysisStatus.Dispatched;
        DispatchedAt = utcNow;
        UpdatedAt = utcNow;
    }

    /// <summary>Dispatched → Completed, storing the result document (Requirement 6.3).</summary>
    public void MarkCompleted(string resultJson, DateTime utcNow)
    {
        if (string.IsNullOrWhiteSpace(resultJson))
            throw new ArgumentException("Result document must not be empty.", nameof(resultJson));
        if (Status != AnalysisStatus.Dispatched)
            throw new InvalidAnalysisTransitionException(Status, "complete");

        Status = AnalysisStatus.Completed;
        ResultJson = resultJson;
        CompletedAt = utcNow;
        UpdatedAt = utcNow;
    }

    /// <summary>
    /// Pending → Failed (dispatch failure) or Dispatched → Failed (analysis failure / timeout),
    /// recording the reason (Requirement 6.4, 10.3, 11.2).
    /// </summary>
    public void MarkFailed(string reason, DateTime utcNow)
    {
        if (string.IsNullOrWhiteSpace(reason))
            throw new ArgumentException("Failure reason must not be empty.", nameof(reason));
        if (Status is not (AnalysisStatus.Pending or AnalysisStatus.Dispatched))
            throw new InvalidAnalysisTransitionException(Status, "fail");

        Status = AnalysisStatus.Failed;
        Error = reason;
        CompletedAt = utcNow;
        UpdatedAt = utcNow;
    }
}
