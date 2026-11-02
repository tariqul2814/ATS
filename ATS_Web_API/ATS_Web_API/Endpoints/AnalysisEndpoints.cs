using ATS_Web_API.Application.Analyses;
using ATS_Web_API.Application.Dtos;
using Microsoft.AspNetCore.Mvc;

namespace ATS_Web_API.Endpoints;

public static class AnalysisEndpoints
{
    public static IEndpointRouteBuilder MapAnalysisEndpoints(this IEndpointRouteBuilder app)
    {
        var group = app.MapGroup("/api/analyses").WithTags("Analyses");

        // POST /api/analyses — submit a résumé + job description (Requirement 1, 5).
        group.MapPost("/", async (
            IFormFileCollection files,
            [FromForm] string? jobDescription,
            StartResumeAnalysisHandler handler,
            CancellationToken ct) =>
        {
            if (files.Count == 0)
                return Results.BadRequest(new { error = "A résumé file is required." });
            if (files.Count > 1)
                return Results.BadRequest(new { error = "Exactly one file may be submitted." });

            var file = files[0];
            await using var stream = file.OpenReadStream();
            var upload = new ResumeUpload(stream, file.FileName, file.ContentType, file.Length);

            var outcome = await handler.HandleAsync(upload, jobDescription, ct);

            return outcome.Error switch
            {
                SubmissionError.None =>
                    Results.Accepted($"/api/analyses/{outcome.Accepted!.AnalysisId}", outcome.Accepted),
                SubmissionError.FileTooLarge =>
                    Results.Problem(outcome.Message, statusCode: StatusCodes.Status413PayloadTooLarge),
                SubmissionError.StorageFailure =>
                    Results.Problem("Could not store the uploaded file.", statusCode: StatusCodes.Status500InternalServerError),
                _ =>
                    Results.BadRequest(new { error = outcome.Message })
            };
        })
        .DisableAntiforgery()
        .WithName("SubmitAnalysis");

        // GET /api/analyses/{analysisId} — status + result, cache-first (Requirement 13).
        group.MapGet("/{analysisId:guid}", async (
            Guid analysisId,
            GetAnalysisStatusHandler handler,
            CancellationToken ct) =>
        {
            var dto = await handler.GetAsync(analysisId, ct);
            return dto is null ? Results.NotFound() : Results.Ok(dto);
        })
        .WithName("GetAnalysisStatus");

        // GET /api/analyses/{analysisId}/result — the full stored JSON document (Requirement 14.4).
        group.MapGet("/{analysisId:guid}/result", async (
            Guid analysisId,
            GetAnalysisStatusHandler handler,
            CancellationToken ct) =>
        {
            var dto = await handler.GetAsync(analysisId, ct);
            if (dto is null) return Results.NotFound();
            if (dto.Status != "Completed" || dto.ResultJson is null)
                return Results.Conflict(new { error = "Result is not available until the analysis is completed." });
            return Results.Content(dto.ResultJson, "application/json");
        })
        .WithName("GetAnalysisResult");

        // GET /api/analyses?ids=g1,g2 — per-GUID history only; NO list-all (Requirement 14).
        group.MapGet("/", async (
            string? ids,
            GetAnalysisHistoryHandler handler,
            CancellationToken ct) =>
        {
            var parsed = (ids ?? string.Empty)
                .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                .Select(s => Guid.TryParse(s, out var g) ? g : (Guid?)null)
                .Where(g => g.HasValue)
                .Select(g => g!.Value)
                .ToArray();

            if (parsed.Length == 0)
                return Results.Ok(Array.Empty<AnalysisHistoryItem>());

            var items = await handler.GetAsync(parsed, ct);
            return Results.Ok(items);
        })
        .WithName("GetAnalysisHistory");

        return app;
    }
}
