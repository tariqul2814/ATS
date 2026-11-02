import { Injectable, signal } from '@angular/core';

export interface AppNotification {
  kind: 'error' | 'info';
  message: string;
}

/** Transient, app-wide notifications (e.g. network/5xx errors surfaced by the interceptor). */
@Injectable({ providedIn: 'root' })
export class NotificationService {
  readonly current = signal<AppNotification | null>(null);

  error(message: string): void {
    this.current.set({ kind: 'error', message });
  }

  info(message: string): void {
    this.current.set({ kind: 'info', message });
  }

  clear(): void {
    this.current.set(null);
  }
}
