import { Component, inject, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';

import { environment } from '../../../environments/environment';
import { AnalysesApiService } from '../../services/analyses-api.service';
import { AnalysisStoreService } from '../../services/analysis-store.service';

@Component({
  selector: 'app-submit',
  imports: [ReactiveFormsModule],
  templateUrl: './submit.html',
  styleUrl: './submit.scss',
})
export class Submit {
  private readonly api = inject(AnalysesApiService);
  private readonly store = inject(AnalysisStoreService);
  private readonly router = inject(Router);

  readonly limits = environment.upload;

  readonly jobDescription = new FormControl('', {
    nonNullable: true,
    validators: [
      Validators.required,
      Validators.maxLength(environment.upload.maxJobDescriptionChars),
    ],
  });

  // Wrapping the control in a FormGroup bound to the <form> is what makes (ngSubmit) fire.
  readonly form = new FormGroup({ jobDescription: this.jobDescription });

  readonly file = signal<File | null>(null);
  readonly fileError = signal<string | null>(null);
  readonly submitting = signal(false);
  readonly submitError = signal<string | null>(null);

  readonly acceptAttr = environment.upload.allowedExtensions.join(',');

  onFileSelected(event: Event): void {
    this.submitError.set(null);
    const input = event.target as HTMLInputElement;
    const picked = input.files?.[0] ?? null;
    this.fileError.set(null);

    if (!picked) {
      this.file.set(null);
      return;
    }

    const name = picked.name.toLowerCase();
    const extOk = this.limits.allowedExtensions.some((ext) => name.endsWith(ext));
    const typeOk = picked.type === '' || this.limits.allowedMimeTypes.includes(picked.type);
    if (!extOk || !typeOk) {
      this.file.set(null);
      this.fileError.set(`Only ${this.limits.allowedExtensions.join(' and ')} files are allowed.`);
      return;
    }
    if (picked.size > this.limits.maxFileSizeBytes) {
      this.file.set(null);
      const mb = (this.limits.maxFileSizeBytes / (1024 * 1024)).toFixed(0);
      this.fileError.set(`File is too large. Maximum size is ${mb} MB.`);
      return;
    }

    this.file.set(picked);
  }

  get canSubmit(): boolean {
    return this.jobDescription.valid && this.file() !== null && !this.submitting();
  }

  submit(): void {
    this.submitError.set(null);
    const file = this.file();
    if (!this.canSubmit || !file) return;

    this.submitting.set(true);
    this.api.submit(file, this.jobDescription.value).subscribe({
      next: (accepted) => {
        this.store.add({
          analysisId: accepted.analysisId,
          fileName: file.name,
          createdAt: new Date().toISOString(),
        });
        this.router.navigate(['/analyses', accepted.analysisId]);
      },
      error: (err: unknown) => {
        this.submitting.set(false);
        this.submitError.set(this.messageFor(err));
      },
    });
  }

  /** Surface the backend's own validation message where it provides one (Requirement 8.1). */
  private messageFor(err: unknown): string {
    if (err instanceof HttpErrorResponse) {
      if (err.status === 413) return 'The file is too large for the server to accept.';
      const body = err.error as { error?: string; detail?: string; title?: string } | string | null;
      if (typeof body === 'string' && body.trim()) return body;
      if (body && typeof body === 'object') {
        return body.error ?? body.detail ?? body.title ?? 'The submission was rejected.';
      }
      return 'The submission was rejected.';
    }
    return 'Something went wrong submitting your analysis. Please try again.';
  }
}
