import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-not-found',
  imports: [RouterLink],
  template: `
    <section class="card">
      <h1>Page not found</h1>
      <p class="muted">That page doesn't exist.</p>
      <a routerLink="/" class="btn">Go home</a>
    </section>
  `,
})
export class NotFound {}
