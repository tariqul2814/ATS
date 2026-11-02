using ATS_Web_API.Domain.Enums;

namespace ATS_Web_API.Domain.Exceptions;

/// <summary>
/// Thrown when a state transition is attempted that the analysis lifecycle does not permit
/// from the current state, including any transition out of a terminal state (Requirement 9.3, 9.4).
/// </summary>
public sealed class InvalidAnalysisTransitionException : Exception
{
    public AnalysisStatus From { get; }
    public string Attempted { get; }

    public InvalidAnalysisTransitionException(AnalysisStatus from, string attempted)
        : base($"Cannot '{attempted}' an analysis while it is in state '{from}'.")
    {
        From = from;
        Attempted = attempted;
    }
}
