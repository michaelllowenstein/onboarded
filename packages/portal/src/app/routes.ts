import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '',          redirectTo: 'nav',     pathMatch: 'full' },
//   { path: 'nav',       loadComponent: () => import('./features/nav').then(m => m.NavComponent) },
//   { path: 'status',    loadComponent: () => import('./features/status').then(m => m.StatusComponent) },
//   { path: 'scan',      loadComponent: () => import('./features/scan').then(m => m.ScanComponent) },
//   { path: 'glossary',  loadComponent: () => import('./features/glossary').then(m => m.GlossaryComponent) },
//   { path: 'queues',    loadComponent: () => import('./features/queues').then(m => m.QueuesComponent) },
//   { path: 'portals',   loadComponent: () => import('./features/portals').then(m => m.PortalsComponent) },
//   { path: 'db',    loadComponent: () => import('./features/db').then(m => m.DbComponent) },
//   { path: 'islands',    loadComponent: () => import('./features/islands').then(m => m.IslandsHost) },
//   { path: 'live-scan', loadComponent: () => import('./features/react-island/react-island-host.component').then(m => m.ReactIslandHostComponent) },
  { path: '**',        redirectTo: 'nav' },
];
