namespace ATS_Web_API.Application;

/// <summary>
/// Raised by the persistence layer when an optimistic-concurrency conflict occurs, so the
/// application layer can react without depending on EF Core types (Requirement 9.6).
/// </summary>
public sealed class ConcurrencyConflictException : Exception
{
    public ConcurrencyConflictException(Exception inner)
        : base("A concurrency conflict occurred while saving the analysis.", inner)
    {
    }
}
