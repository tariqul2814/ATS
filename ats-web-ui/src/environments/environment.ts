/**
 * Production / default environment.
 * Overridden in development by environment.development.ts (see angular.json fileReplacements).
 */
export const environment = {
  production: true,
  /** Base URL of the .NET orchestrator API, e.g. https://api.example.com */
  apiBaseUrl: '',
  /** Absolute URL of the SignalR hub, e.g. https://api.example.com/hubs/analysis */
  hubUrl: '',
  /** Client-side upload constraints kept aligned with the backend (authoritative) limits. */
  upload: {
    maxFileSizeBytes: 5 * 1024 * 1024, // 5 MB (backend Uploads:MaxFileSizeBytes)
    allowedExtensions: ['.pdf', '.docx'],
    allowedMimeTypes: [
      'application/pdf',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    ],
    maxJobDescriptionChars: 20000, // backend Uploads:MaxJobDescriptionChars
  },
};
