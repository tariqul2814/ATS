using ATS_Web_API.Domain.Entities;
using ATS_Web_API.Domain.Enums;
using ATS_Web_API.Domain.Exceptions;
using FluentAssertions;
using Xunit;

namespace ATS_Web_API.Tests.Domain;

public class ResumeAnalysisTests
{
    private static readonly DateTime T0 = new(2026, 10, 13, 10, 0, 0, DateTimeKind.Utc);
    private static readonly DateTime T1 = T0.AddMinutes(1);

    private static ResumeAnalysis NewPending() => ResumeAnalysis.Create("Senior .NET engineer", T0);

    private static ResumeAnalysis NewDispatched()
    {
        var a = NewPending();
        a.MarkDispatched(T0);
        return a;
    }

    private static ResumeAnalysis NewCompleted()
    {
        var a = NewDispatched();
        a.MarkCompleted("{\"score\":80}", T0);
        return a;
    }

    private static ResumeAnalysis NewFailed()
    {
        var a = NewDispatched();
        a.MarkFailed("boom", T0);
        return a;
    }

    // ---- Create (Req 3.1, 3.3) ----

    [Fact]
    public void Create_StartsPending_WithIdAndTimestamps()
    {
        var a = ResumeAnalysis.Create("JD text", T0);

        a.Id.Should().NotBe(Guid.Empty);
        a.Status.Should().Be(AnalysisStatus.Pending);
        a.JobDescription.Should().Be("JD text");
        a.CreatedAt.Should().Be(T0);
        a.UpdatedAt.Should().Be(T0);
        a.DispatchedAt.Should().BeNull();
        a.CompletedAt.Should().BeNull();
        a.ResumeFileReference.Should().BeNull();
        a.ResultJson.Should().BeNull();
        a.Error.Should().BeNull();
    }

    [Fact]
    public void Create_GeneratesUniqueIds()
    {
        ResumeAnalysis.Create("x", T0).Id
            .Should().NotBe(ResumeAnalysis.Create("x", T0).Id);
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData(null)]
    public void Create_RejectsEmptyJobDescription(string? jd)
    {
        var act = () => ResumeAnalysis.Create(jd!, T0);
        act.Should().Throw<ArgumentException>();
    }

    // ---- AttachResume (Req 2.2) ----

    [Fact]
    public void AttachResume_WhilePending_SetsReferenceAndStampsUpdatedAt()
    {
        var a = NewPending();

        a.AttachResume("abc.pdf", T1);

        a.ResumeFileReference.Should().Be("abc.pdf");
        a.UpdatedAt.Should().Be(T1);
    }

    [Fact]
    public void AttachResume_AfterDispatched_Throws()
    {
        var a = NewDispatched();

        var act = () => a.AttachResume("abc.pdf", T1);

        act.Should().Throw<InvalidAnalysisTransitionException>();
    }

    // ---- Allowed transitions (Req 9.2) ----

    [Fact]
    public void MarkDispatched_FromPending_Transitions()
    {
        var a = NewPending();

        a.MarkDispatched(T1);

        a.Status.Should().Be(AnalysisStatus.Dispatched);
        a.DispatchedAt.Should().Be(T1);
        a.UpdatedAt.Should().Be(T1);
    }

    [Fact]
    public void MarkCompleted_FromDispatched_Transitions()
    {
        var a = NewDispatched();

        a.MarkCompleted("{\"score\":92}", T1);

        a.Status.Should().Be(AnalysisStatus.Completed);
        a.ResultJson.Should().Be("{\"score\":92}");
        a.CompletedAt.Should().Be(T1);
        a.UpdatedAt.Should().Be(T1);
    }

    [Fact]
    public void MarkFailed_FromPending_Transitions()
    {
        var a = NewPending();

        a.MarkFailed("dispatch_failed", T1);

        a.Status.Should().Be(AnalysisStatus.Failed);
        a.Error.Should().Be("dispatch_failed");
        a.CompletedAt.Should().Be(T1);
        a.UpdatedAt.Should().Be(T1);
    }

    [Fact]
    public void MarkFailed_FromDispatched_Transitions()
    {
        var a = NewDispatched();

        a.MarkFailed("dispatch_timeout", T1);

        a.Status.Should().Be(AnalysisStatus.Failed);
        a.Error.Should().Be("dispatch_timeout");
    }

    // ---- Disallowed transitions, including out of terminal states (Req 9.3, 9.4) ----

    [Fact]
    public void MarkDispatched_FromNonPending_Throws()
    {
        new Action(() => NewDispatched().MarkDispatched(T1)).Should().Throw<InvalidAnalysisTransitionException>();
        new Action(() => NewCompleted().MarkDispatched(T1)).Should().Throw<InvalidAnalysisTransitionException>();
        new Action(() => NewFailed().MarkDispatched(T1)).Should().Throw<InvalidAnalysisTransitionException>();
    }

    [Fact]
    public void MarkCompleted_FromNonDispatched_Throws()
    {
        new Action(() => NewPending().MarkCompleted("{}", T1)).Should().Throw<InvalidAnalysisTransitionException>();
        new Action(() => NewCompleted().MarkCompleted("{}", T1)).Should().Throw<InvalidAnalysisTransitionException>();
        new Action(() => NewFailed().MarkCompleted("{}", T1)).Should().Throw<InvalidAnalysisTransitionException>();
    }

    [Fact]
    public void MarkFailed_FromTerminal_Throws()
    {
        new Action(() => NewCompleted().MarkFailed("x", T1)).Should().Throw<InvalidAnalysisTransitionException>();
        new Action(() => NewFailed().MarkFailed("x", T1)).Should().Throw<InvalidAnalysisTransitionException>();
    }

    [Fact]
    public void TerminalState_IsNotMutated_WhenDisallowedTransitionThrows()
    {
        var a = NewCompleted();

        new Action(() => a.MarkFailed("x", T1)).Should().Throw<InvalidAnalysisTransitionException>();

        a.Status.Should().Be(AnalysisStatus.Completed);
        a.Error.Should().BeNull();
    }
}
