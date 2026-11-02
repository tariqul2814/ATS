using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using ATS_Web_API.Application.Dtos;
using FluentAssertions;
using Xunit;

namespace ATS_Web_API.Tests.Integration;

public class SubmissionEndpointTests : IClassFixture<ApiFactory>
{
    private readonly ApiFactory _factory;

    public SubmissionEndpointTests(ApiFactory factory) => _factory = factory;

    private static readonly byte[] PdfBytes = { 0x25, 0x50, 0x44, 0x46, 0x2D, 0x31, 0x2E, 0x34 }; // %PDF-1.4

    private static MultipartFormDataContent BuildForm(byte[] fileBytes, string fileName, string contentType, string? jobDescription)
    {
        var form = new MultipartFormDataContent();
        var file = new ByteArrayContent(fileBytes);
        file.Headers.ContentType = new MediaTypeHeaderValue(contentType);
        form.Add(file, "files", fileName);
        if (jobDescription is not null)
            form.Add(new StringContent(jobDescription), "jobDescription");
        return form;
    }

    [Fact]
    public async Task ValidSubmission_Returns202_WithAnalysisId()
    {
        var client = _factory.CreateClient();

        var response = await client.PostAsync("/api/analyses",
            BuildForm(PdfBytes, "cv.pdf", "application/pdf", "Senior .NET engineer"));

        response.StatusCode.Should().Be(HttpStatusCode.Accepted);
        var body = await response.Content.ReadFromJsonAsync<AnalysisAccepted>();
        body!.AnalysisId.Should().NotBe(Guid.Empty);
        body.Status.Should().Be("Dispatched"); // fake dispatcher accepts (202), so it advances
        _factory.Dispatcher.Requests.Should().ContainSingle(r => r.AnalysisId == body.AnalysisId);
    }

    [Fact]
    public async Task WrongFileType_Returns400()
    {
        var client = _factory.CreateClient();

        var response = await client.PostAsync("/api/analyses",
            BuildForm(new byte[] { 1, 2, 3 }, "note.txt", "text/plain", "jd"));

        response.StatusCode.Should().Be(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task MissingJobDescription_Returns400()
    {
        var client = _factory.CreateClient();

        var response = await client.PostAsync("/api/analyses",
            BuildForm(PdfBytes, "cv.pdf", "application/pdf", jobDescription: null));

        response.StatusCode.Should().Be(HttpStatusCode.BadRequest);
    }

    [Fact]
    public async Task NoFile_Returns400()
    {
        var client = _factory.CreateClient();

        var form = new MultipartFormDataContent { { new StringContent("jd"), "jobDescription" } };
        var response = await client.PostAsync("/api/analyses", form);

        response.StatusCode.Should().Be(HttpStatusCode.BadRequest);
    }
}
