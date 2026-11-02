/**
 * Development environment. Points at the local .NET orchestrator (see its launchSettings.json:
 * https profile applicationUrl https://localhost:7120). The SPA is served from http://localhost:4200,
 * which is the backend's configured allowed CORS origin.
 */
export const environment = {
  production: false,
  apiBaseUrl: 'https://localhost:7120',
  hubUrl: 'https://localhost:7120/hubs/analysis',
  upload: {
    maxFileSizeBytes: 5 * 1024 * 1024, // 5 MB
    allowedExtensions: ['.pdf', '.docx'],
    allowedMimeTypes: [
      'application/pdf',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    ],
    maxJobDescriptionChars: 20000,
  },
};
