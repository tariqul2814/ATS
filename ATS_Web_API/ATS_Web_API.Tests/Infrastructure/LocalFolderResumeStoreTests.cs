using ATS_Web_API.Application.Options;
using ATS_Web_API.Infrastructure.Storage;
using FluentAssertions;
using Microsoft.Extensions.Options;
using Xunit;

namespace ATS_Web_API.Tests.Infrastructure;

public class LocalFolderResumeStoreTests
{
    [Fact]
    public async Task SaveAsync_WritesFileUnderRoot_AndReturnsFullPath()
    {
        var root = Path.Combine(Path.GetTempPath(), "ats-store-test", Guid.NewGuid().ToString("N"));
        try
        {
            var store = new LocalFolderResumeStore(Options.Create(new StorageOptions { Root = root }));
            var id = Guid.NewGuid();
            var data = new byte[] { 1, 2, 3, 4, 5 };

            using var input = new MemoryStream(data);
            var fullPath = await store.SaveAsync(id, input, ".pdf", default);

            fullPath.Should().Be(Path.Combine(root, $"{id}.pdf"));
            File.Exists(fullPath).Should().BeTrue();
            (await File.ReadAllBytesAsync(fullPath)).Should().Equal(data);
        }
        finally
        {
            if (Directory.Exists(root)) Directory.Delete(root, recursive: true);
        }
    }
}
