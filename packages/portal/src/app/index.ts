import { Component, inject, signal } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { DomainService } from './core/services/domain';

interface NavItem {
  path: string;
  label: string;
  icon: string;
}

@Component({
  selector: 'ob-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './index.html',
  styleUrls: ['./index.scss']
})
export class App {
  protected readonly domain: DomainService = inject(DomainService);
  protected readonly sidebarCollapsed = signal(false);

  protected readonly navItems: NavItem[] = [
    { path: 'nav',       label: 'Operations',  icon: '⊞' },
    { path: 'status',    label: 'Status Codes', icon: '◎' },
    { path: 'glossary',  label: 'Glossary',    icon: '⊜' },
    { path: 'scan',      label: 'Scan Rules',  icon: '⊗' },
    { path: 'queues',    label: 'Queues',      icon: '⇄' },
    { path: 'portals',   label: 'Portals',     icon: '◇' },
    { path: 'live-scan', label: 'Live Scan',   icon: '▣' },
  ];
}
