using ATS_Web_API.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace ATS_Web_API.Infrastructure.Persistence;

public sealed class ResumeAnalysisConfiguration : IEntityTypeConfiguration<ResumeAnalysis>
{
    public void Configure(EntityTypeBuilder<ResumeAnalysis> e)
    {
        e.ToTable("ResumeAnalyses");

        e.HasKey(x => x.Id);
        e.Property(x => x.Id).ValueGeneratedNever(); // GUID assigned by the domain (Req 3.1)

        e.Property(x => x.Status)
            .HasConversion<string>()
            .HasMaxLength(20)
            .IsRequired();

        e.Property(x => x.ResumeFileReference).HasMaxLength(512);
        e.Property(x => x.JobDescription).IsRequired();
        e.Property(x => x.ResultJson); // nvarchar(max) single JSON document (Req 3.5)
        e.Property(x => x.Error).HasMaxLength(1024);

        e.Property(x => x.CreatedAt).IsRequired();
        e.Property(x => x.UpdatedAt).IsRequired();

        // Optimistic-concurrency token for the webhook-vs-sweeper race guard (Req 9.6).
        e.Property(x => x.RowVersion).IsRowVersion();

        // Supports the sweeper's "stalled Dispatched" query efficiently (Req 11, 19.4).
        e.HasIndex(x => new { x.Status, x.DispatchedAt });
    }
}
