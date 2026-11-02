using ATS_Web_API.Endpoints;
using FluentAssertions;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace ATS_Web_API.Tests.Application;

public class GlobalExceptionHandlerTests
{
    [Fact]
    public async Task TryHandle_Writes500ProblemDetails_WithoutLeakingExceptionDetail()
    {
        var context = new DefaultHttpContext { Response = { Body = new MemoryStream() } };
        var handler = new GlobalExceptionHandler(NullLogger<GlobalExceptionHandler>.Instance);

        var handled = await handler.TryHandleAsync(
            context, new InvalidOperationException("secret connection string leaked"), default);

        handled.Should().BeTrue();
        context.Response.StatusCode.Should().Be(StatusCodes.Status500InternalServerError);

        context.Response.Body.Position = 0;
        var body = await new StreamReader(context.Response.Body).ReadToEndAsync();
        body.Should().Contain("unexpected error");
        body.Should().NotContain("secret connection string leaked");
    }
}
