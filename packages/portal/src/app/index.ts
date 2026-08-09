import { Component, inject, signal } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
// import { DomainService } from './core/services/domain.service';

interface NavItem {
  path: string;
  label: string;
  icon: string;
}

@Component({
  selector: 'ob-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <div class="ob-shell" [class.sidebar-collapsed]="sidebarCollapsed()">
      <!-- Sidebar -->
      <aside class="ob-sidebar">
        <div class="ob-sidebar__header">
          <div class="ob-brand">
            <span class="ob-brand__icon">◆</span>
            <span class="ob-brand__text" *ngIf="!sidebarCollapsed()">
              {{ domain.brandName }}
            </span>
          </div>
          <button
            class="ob-sidebar__toggle"
            (click)="sidebarCollapsed.set(!sidebarCollapsed())"
            [attr.aria-label]="sidebarCollapsed() ? 'Expand sidebar' : 'Collapse sidebar'"
          >
            {{ sidebarCollapsed() ? '▸' : '◂' }}
          </button>
        </div>

        <nav class="ob-sidebar__nav">
          @for (item of navItems; track item.path) {
            <a
              class="ob-nav-link"
              [routerLink]="item.path"
              routerLinkActive="ob-nav-link--active"
            >
              <span class="ob-nav-link__icon">{{ item.icon }}</span>
              @if (!sidebarCollapsed()) {
                <span class="ob-nav-link__label">{{ item.label }}</span>
              }
            </a>
          }
        </nav>

        <div class="ob-sidebar__footer">
          <span class="ob-sidebar__meta">
            @if (!sidebarCollapsed()) {
              {{ domain.cliName }} · v4.0.0
            }
          </span>
        </div>
      </aside>

      <!-- Main content -->
      <main class="ob-main">
        <router-outlet />
      </main>
    </div>
  `,
  styles: [`
    :host {
      display: block;
      height: 100vh;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }

    .ob-shell {
      display: grid;
      grid-template-columns: 240px 1fr;
      height: 100%;
      transition: grid-template-columns 0.2s ease;
    }

    .ob-shell.sidebar-collapsed {
      grid-template-columns: 56px 1fr;
    }

    .ob-sidebar {
      background: var(--ob-sidebar-bg, #0f1117);
      border-right: 1px solid var(--ob-border, #1e2030);
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    .ob-sidebar__header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 16px 12px;
      border-bottom: 1px solid var(--ob-border, #1e2030);
    }

    .ob-brand {
      display: flex;
      align-items: center;
      gap: 8px;
      white-space: nowrap;
      overflow: hidden;
    }

    .ob-brand__icon {
      color: var(--ob-accent, #7c6ef6);
      font-size: 18px;
      flex-shrink: 0;
    }

    .ob-brand__text {
      color: var(--ob-text-primary, #e2e0d8);
      font-weight: 600;
      font-size: 14px;
    }

    .ob-sidebar__toggle {
      background: none;
      border: none;
      color: var(--ob-text-muted, #8b8a82);
      cursor: pointer;
      padding: 4px;
      font-size: 14px;
      flex-shrink: 0;
    }

    .ob-sidebar__nav {
      flex: 1;
      padding: 8px 6px;
      overflow-y: auto;
    }

    .ob-nav-link {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 10px;
      border-radius: 6px;
      color: var(--ob-text-secondary, #a8a7a0);
      text-decoration: none;
      font-size: 13px;
      transition: background 0.15s, color 0.15s;
      white-space: nowrap;
    }

    .ob-nav-link:hover {
      background: var(--ob-hover, #1a1d2e);
      color: var(--ob-text-primary, #e2e0d8);
    }

    .ob-nav-link--active {
      background: var(--ob-active-bg, #1e1f3a);
      color: var(--ob-accent, #7c6ef6);
      font-weight: 500;
    }

    .ob-nav-link__icon {
      font-size: 15px;
      flex-shrink: 0;
      width: 20px;
      text-align: center;
    }

    .ob-sidebar__footer {
      padding: 12px;
      border-top: 1px solid var(--ob-border, #1e2030);
    }

    .ob-sidebar__meta {
      color: var(--ob-text-muted, #8b8a82);
      font-size: 11px;
    }

    .ob-main {
      background: var(--ob-main-bg, #13141c);
      overflow-y: auto;
      padding: 24px 32px;
      color: var(--ob-text-primary, #e2e0d8);
    }
  `],
})
export class App {
  // protected readonly domain = inject(DomainService);
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
