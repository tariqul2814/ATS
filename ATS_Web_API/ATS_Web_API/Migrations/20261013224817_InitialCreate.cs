using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace ATS_Web_API.Migrations
{
    /// <inheritdoc />
    public partial class InitialCreate : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "ResumeAnalyses",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uniqueidentifier", nullable: false),
                    Status = table.Column<string>(type: "nvarchar(20)", maxLength: 20, nullable: false),
                    ResumeFileReference = table.Column<string>(type: "nvarchar(512)", maxLength: 512, nullable: true),
                    JobDescription = table.Column<string>(type: "nvarchar(max)", nullable: false),
                    ResultJson = table.Column<string>(type: "nvarchar(max)", nullable: true),
                    Error = table.Column<string>(type: "nvarchar(1024)", maxLength: 1024, nullable: true),
                    CreatedAt = table.Column<DateTime>(type: "datetime2", nullable: false),
                    UpdatedAt = table.Column<DateTime>(type: "datetime2", nullable: false),
                    DispatchedAt = table.Column<DateTime>(type: "datetime2", nullable: true),
                    CompletedAt = table.Column<DateTime>(type: "datetime2", nullable: true),
                    RowVersion = table.Column<byte[]>(type: "rowversion", rowVersion: true, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ResumeAnalyses", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_ResumeAnalyses_Status_DispatchedAt",
                table: "ResumeAnalyses",
                columns: new[] { "Status", "DispatchedAt" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "ResumeAnalyses");
        }
    }
}
