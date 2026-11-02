using ATS_Web_API.Application.Options;
using FluentAssertions;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using Xunit;

namespace ATS_Web_API.Tests.Configuration;

public class OptionsValidationTests
{
    private static T Resolve<T>(string section, Dictionary<string, string?> config) where T : class
    {
        var configuration = new ConfigurationBuilder().AddInMemoryCollection(config).Build();
        var services = new ServiceCollection();
        services.AddOptions<T>()
            .Bind(configuration.GetSection(section))
            .ValidateDataAnnotations();
        var provider = services.BuildServiceProvider();
        return provider.GetRequiredService<IOptions<T>>().Value;
    }

    [Fact]
    public void Webhook_MissingSecret_FailsValidation()
    {
        var act = () => Resolve<WebhookOptions>(WebhookOptions.SectionName, new()
        {
            ["Webhook:PublicCallbackUrl"] = "https://host/cb",
            ["Webhook:ToleranceSeconds"] = "300"
            // Secret intentionally absent
        });

        act.Should().Throw<OptionsValidationException>();
    }

    [Fact]
    public void Storage_MissingRoot_FailsValidation()
    {
        var act = () => Resolve<StorageOptions>(StorageOptions.SectionName, new());
        act.Should().Throw<OptionsValidationException>();
    }

    [Fact]
    public void FastApi_InvalidBaseUrl_FailsValidation()
    {
        var act = () => Resolve<FastApiOptions>(FastApiOptions.SectionName, new()
        {
            ["FastApi:BaseUrl"] = "not-a-url",
            ["FastApi:DispatchPath"] = "/analyze"
        });

        act.Should().Throw<OptionsValidationException>();
    }

    [Fact]
    public void Webhook_ValidConfig_Passes()
    {
        var opts = Resolve<WebhookOptions>(WebhookOptions.SectionName, new()
        {
            ["Webhook:Secret"] = "0123456789abcdef",
            ["Webhook:PublicCallbackUrl"] = "https://host/cb",
            ["Webhook:ToleranceSeconds"] = "300"
        });

        opts.Secret.Should().Be("0123456789abcdef");
        opts.ToleranceSeconds.Should().Be(300);
    }
}
