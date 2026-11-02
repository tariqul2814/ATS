import { Injectable } from '@angular/core';
import {
  HubConnection,
  HubConnectionBuilder,
  HubConnectionState,
  LogLevel,
} from '@microsoft/signalr';
import { Observable, Subject } from 'rxjs';

import { environment } from '../../environments/environment';
import { AnalysisStatusDto } from '../models/analysis';

/**
 * Wraps the SignalR connection to the orchestrator's `/hubs/analysis` hub (Requirement 3).
 * A caller subscribes to a single analysis id and receives `analysisUpdated` payloads; it must
 * call stop() when done so the connection is not leaked (Requirement 3.5).
 */
@Injectable()
export class AnalysisHubService {
  private connection?: HubConnection;
  private readonly updates$ = new Subject<AnalysisStatusDto>();

  /** Emits each `analysisUpdated` push for the subscribed analysis. */
  readonly updates: Observable<AnalysisStatusDto> = this.updates$.asObservable();

  /**
   * Connect, subscribe to the given analysis id, and (re)subscribe automatically on reconnect
   * (Requirement 3.6). `onReconnected` lets the caller reconcile current status via the API.
   */
  async start(analysisId: string, onReconnected?: () => void): Promise<void> {
    this.connection = new HubConnectionBuilder()
      .withUrl(environment.hubUrl)
      .withAutomaticReconnect()
      .configureLogging(environment.production ? LogLevel.Error : LogLevel.Information)
      .build();

    this.connection.on('analysisUpdated', (dto: AnalysisStatusDto) => this.updates$.next(dto));

    this.connection.onreconnected(async () => {
      await this.subscribe(analysisId);
      onReconnected?.();
    });

    await this.connection.start();
    await this.subscribe(analysisId);
  }

  private subscribe(analysisId: string): Promise<void> {
    // Matches AnalysisHub.SubscribeToAnalysis(Guid) on the server.
    return this.connection?.invoke('SubscribeToAnalysis', analysisId) ?? Promise.resolve();
  }

  /** Whether a live connection currently exists. */
  get connected(): boolean {
    return this.connection?.state === HubConnectionState.Connected;
  }

  /** Tear down the connection and complete the stream. */
  async stop(): Promise<void> {
    try {
      await this.connection?.stop();
    } finally {
      this.connection = undefined;
      this.updates$.complete();
    }
  }
}
