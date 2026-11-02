import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';

import { NotificationService } from '../services/notification.service';

/**
 * Centralized HTTP error handling (Requirement 8.4). Network failures and 5xx responses are
 * surfaced as a global notification; all errors are re-thrown so components can still react
 * contextually (e.g. 400 on the form, 409 "in progress" on the result endpoint — Requirement 8.5).
 */
export const httpErrorInterceptor: HttpInterceptorFn = (req, next) => {
  const notifications = inject(NotificationService);

  return next(req).pipe(
    catchError((error: unknown) => {
      if (error instanceof HttpErrorResponse) {
        if (error.status === 0) {
          notifications.error('Cannot reach the server. Check your connection and try again.');
        } else if (error.status >= 500) {
          notifications.error('Something went wrong on the server. Please try again shortly.');
        }
        // 4xx (400/404/409/413) are left for the calling component to handle in context.
      }
      return throwError(() => error);
    }),
  );
};
