namespace ATS_Web_API.Domain.Enums;

/// <summary>
/// Lifecycle states of a <see cref="Entities.ResumeAnalysis"/> (Requirement 9.1).
/// Allowed transitions: Pending→Dispatched, Pending→Failed, Dispatched→Completed, Dispatched→Failed.
/// Completed and Failed are terminal.
/// </summary>
public enum AnalysisStatus
{
    Pending = 0,
    Dispatched = 1,
    Completed = 2,
    Failed = 3
}
