using ATS_Web_API.Domain.Entities;
using FluentAssertions;
using Xunit;

namespace ATS_Web_API.Tests;

/// <summary>
/// Enforces the clean-layered dependency rule in the single-project layout: Domain depends on
/// nothing in the outer layers or on framework infrastructure (Task 17.4).
/// </summary>
public class ArchitectureTests
{
    private static readonly string[] ForbiddenPrefixes =
    {
        "ATS_Web_API.Application",
        "ATS_Web_API.Infrastructure",
        "ATS_Web_API.Endpoints",
        "Microsoft.EntityFrameworkCore",
        "Microsoft.AspNetCore"
    };

    [Fact]
    public void DomainTypes_DoNotReferenceOuterLayersOrFrameworks()
    {
        var assembly = typeof(ResumeAnalysis).Assembly;
        var domainTypes = assembly.GetTypes()
            .Where(t => t.Namespace?.StartsWith("ATS_Web_API.Domain", StringComparison.Ordinal) == true);

        var violations = new List<string>();

        foreach (var type in domainTypes)
        {
            var referenced = new List<Type>();
            referenced.AddRange(type.GetProperties().Select(p => p.PropertyType));
            referenced.AddRange(type.GetFields(System.Reflection.BindingFlags.Instance |
                                               System.Reflection.BindingFlags.Static |
                                               System.Reflection.BindingFlags.Public |
                                               System.Reflection.BindingFlags.NonPublic)
                                     .Select(f => f.FieldType));
            foreach (var ctor in type.GetConstructors(System.Reflection.BindingFlags.Instance |
                                                      System.Reflection.BindingFlags.Public |
                                                      System.Reflection.BindingFlags.NonPublic))
                referenced.AddRange(ctor.GetParameters().Select(p => p.ParameterType));
            foreach (var method in type.GetMethods(System.Reflection.BindingFlags.Instance |
                                                   System.Reflection.BindingFlags.Static |
                                                   System.Reflection.BindingFlags.Public |
                                                   System.Reflection.BindingFlags.DeclaredOnly))
            {
                referenced.Add(method.ReturnType);
                referenced.AddRange(method.GetParameters().Select(p => p.ParameterType));
            }

            foreach (var referencedType in referenced.SelectMany(Expand))
            {
                var ns = referencedType.Namespace;
                if (ns is null) continue;
                if (ForbiddenPrefixes.Any(p => ns.StartsWith(p, StringComparison.Ordinal)))
                    violations.Add($"{type.Name} references {referencedType.FullName}");
            }
        }

        violations.Should().BeEmpty();
    }

    private static IEnumerable<Type> Expand(Type type)
    {
        yield return type;
        if (type.IsArray && type.GetElementType() is { } element)
            yield return element;
        if (type.IsGenericType)
            foreach (var arg in type.GetGenericArguments())
                yield return arg;
    }
}
