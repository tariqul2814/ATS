using ATS_Web_API.Application.Abstractions;
using ATS_Web_API.Application.Analyses;
using ATS_Web_API.Application.Options;
using ATS_Web_API.Endpoints;
using System.Net;
using ATS_Web_API.Infrastructure.BackgroundServices;
using ATS_Web_API.Infrastructure.Cache;
using ATS_Web_API.Infrastructure.Dispatch;
using ATS_Web_API.Infrastructure.Health;
using ATS_Web_API.Infrastructure.Persistence;
using ATS_Web_API.Infrastructure.Push;
using ATS_Web_API.Infrastructure.Security;
using ATS_Web_API.Infrastructure.Storage;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Http.Resilience;
using Microsoft.Extensions.Options;
using Polly;
using Polly.Timeout;

var builder = WebApplication.CreateBuilder(args);

// --- Configuration (Requirement 15): bind + validate all external settings, fail fast at startup. ---
void AddValidatedOptions<T>(string section) where T : class =>
    builder.Services.AddOptions<T>()
        .Bind(builder.Configuration.GetSection(section))
        .ValidateDataAnnotations()
        .ValidateOnStart();

AddValidatedOptions<FastApiOptions>(FastApiOptions.SectionName);
AddValidatedOptions<StorageOptions>(StorageOptions.SectionName);
AddValidatedOptions<WebhookOptions>(WebhookOptions.SectionName);
AddValidatedOptions<AnalysisOptions>(AnalysisOptions.SectionName);
AddValidatedOptions<UploadsOptions>(UploadsOptions.SectionName);
AddValidatedOptions<CorsOptions>(CorsOptions.SectionName);
AddValidatedOptions<DispatchOptions>(DispatchOptions.SectionName);

// --- Persistence (Requirement 3) ---
builder.Services.AddDbContext<AppDbContext>(o =>
    o.UseSqlServer(builder.Configuration.GetConnectionString("SqlServer")));
builder.Services.AddScoped<IAnalysisRepository, AnalysisRepository>();

// --- Résumé storage (Requirement 2) ---
builder.Services.AddScoped<IResumeStore, LocalFolderResumeStore>();

// --- In-memory status cache (Requirement 12.3, 13) ---
builder.Services.AddMemoryCache();
builder.Services.AddSingleton<IAnalysisStatusCache, InMemoryAnalysisStatusCache>();

// --- Webhook signature verification (Requirement 7) ---
builder.Services.AddSingleton<IWebhookSignatureVerifier, HmacWebhookSignatureVerifier>();

// --- Real-time push via SignalR (Requirement 12) ---
builder.Services.AddSignalR();
builder.Services.AddScoped<IAnalysisNotifier, SignalRAnalysisNotifier>();

// --- Timeout sweeper (Requirement 11) ---
builder.Services.AddScoped<StalledAnalysisSweepService>();
builder.Services.AddHostedService<StalledAnalysisSweeper>();

// --- Dispatch to FastAPI with a transient-fault retry policy (Requirement 4, 10) ---
builder.Services.AddHttpClient<IAnalysisDispatcher, FastApiAnalysisDispatcher>((sp, client) =>
{
    var fast = sp.GetRequiredService<IOptions<FastApiOptions>>().Value;
    client.BaseAddress = new Uri(fast.BaseUrl);
    client.Timeout = Timeout.InfiniteTimeSpan; // per-attempt timeout is handled by the resilience pipeline
})
.AddResilienceHandler("fastapi-dispatch", (pipeline, context) =>
{
    var dispatch = context.ServiceProvider.GetRequiredService<IOptions<DispatchOptions>>().Value;
    var fast = context.ServiceProvider.GetRequiredService<IOptions<FastApiOptions>>().Value;

    pipeline.AddRetry(new HttpRetryStrategyOptions
    {
        MaxRetryAttempts = dispatch.RetryCount,
        BackoffType = DelayBackoffType.Exponential,
        UseJitter = true,
        Delay = TimeSpan.FromSeconds(dispatch.BaseDelaySeconds),
        ShouldHandle = args => ValueTask.FromResult(
            args.Outcome.Exception is HttpRequestException or TimeoutRejectedException ||
            (args.Outcome.Result is { } r &&
             ((int)r.StatusCode >= 500 || r.StatusCode == HttpStatusCode.RequestTimeout)))
    });

    pipeline.AddTimeout(TimeSpan.FromSeconds(fast.DispatchHttpTimeoutSeconds));
});

// --- Application use-case handlers ---
builder.Services.AddSingleton(TimeProvider.System);
builder.Services.AddScoped<StartResumeAnalysisHandler>();
builder.Services.AddScoped<RecordAnalysisResultHandler>();
builder.Services.AddScoped<GetAnalysisStatusHandler>();
builder.Services.AddScoped<GetAnalysisHistoryHandler>();

// Cap multipart uploads a bit above the configured file-size limit (Requirement 1.5).
var maxFileSize = builder.Configuration.GetValue<long>("Uploads:MaxFileSizeBytes", 5 * 1024 * 1024);
builder.Services.Configure<FormOptions>(o => o.MultipartBodyLengthLimit = maxFileSize + 1_048_576);

// --- Cross-cutting: error handling, CORS, health (Requirement 16, 18.5) ---
builder.Services.AddProblemDetails();
builder.Services.AddExceptionHandler<GlobalExceptionHandler>();

var allowedOrigins = builder.Configuration.GetSection($"{CorsOptions.SectionName}:AllowedOrigins").Get<string[]>()
                     ?? Array.Empty<string>();
builder.Services.AddCors(o => o.AddDefaultPolicy(p =>
{
    p.AllowAnyHeader().AllowAnyMethod().AllowCredentials();

    // The dev server's host and port vary (localhost vs 127.0.0.1, ng serve picking another port),
    // so Development accepts any loopback origin; every other environment uses the exact list.
    if (builder.Environment.IsDevelopment())
        p.SetIsOriginAllowed(origin =>
            allowedOrigins.Contains(origin, StringComparer.OrdinalIgnoreCase) ||
            (Uri.TryCreate(origin, UriKind.Absolute, out var uri) && uri.IsLoopback));
    else
        p.WithOrigins(allowedOrigins);
}));

builder.Services.AddSingleton<ReadinessHealthCheck>();
builder.Services.AddHealthChecks().AddCheck<ReadinessHealthCheck>("ready");

builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

var app = builder.Build();

app.UseExceptionHandler();

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

// Redirect browsers to HTTPS, but not the FastAPI webhook: a server-to-server signed POST cannot
// follow a redirect, and the HMAC signature (Req 7), not TLS, is what authenticates the callback.
app.UseWhen(
    ctx => !ctx.Request.Path.StartsWithSegments("/api/webhooks"),
    branch => branch.UseHttpsRedirection());
app.UseCors();

app.MapAnalysisEndpoints();
app.MapWebhookEndpoints();
app.MapHub<AnalysisHub>("/hubs/analysis");
app.MapHealthChecks("/health");

app.Run();

// Exposed so the integration test project (WebApplicationFactory<Program>) can host the app.
public partial class Program { }
