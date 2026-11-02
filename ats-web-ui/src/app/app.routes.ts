import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./features/submit/submit').then((m) => m.Submit),
    title: 'Submit a CV · ATS Checker',
  },
  {
    path: 'history',
    loadComponent: () => import('./features/history/history').then((m) => m.History),
    title: 'Your analyses · ATS Checker',
  },
  {
    path: 'analyses/:id',
    loadComponent: () =>
      import('./features/analysis-detail/analysis-detail').then((m) => m.AnalysisDetail),
    title: 'Analysis · ATS Checker',
  },
  {
    path: '**',
    loadComponent: () => import('./features/not-found/not-found').then((m) => m.NotFound),
    title: 'Not found · ATS Checker',
  },
];
