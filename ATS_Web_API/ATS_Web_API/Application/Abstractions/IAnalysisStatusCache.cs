using ATS_Web_API.Application.Dtos;

namespace ATS_Web_API.Application.Abstractions;

/// <summary>Cache of the latest analysis status, independent of the primary DB read path (Req 12.3, 13).</summary>
public interface IAnalysisStatusCache
{
    void Set(AnalysisStatusDto status);
    bool TryGet(Guid analysisId, out AnalysisStatusDto? status);
}
