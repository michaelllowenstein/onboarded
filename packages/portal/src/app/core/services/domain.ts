import { Injectable } from '@angular/core';
import { environment } from '../../../envs/env';
import type { TenantDomain, Operation, ScanRule, GlossaryTerm } from '@onboarded/shared';

/**
 * DomainService — providedIn: 'root' because the app shell reads brandName
 * on first paint for sidebar rendering. Lazy-providing this would leave the
 * sidebar empty until the first route activated.
 *
 * The domain data is injected at build time via the TENANT_DOMAIN constant
 * imported through the environment file. Zero HTTP dependency for nav data.
 */
@Injectable({ providedIn: 'root' })
export class DomainService {
  private readonly domain: TenantDomain = environment.tenantDomain;

  get brandName(): string { return this.domain.tenant.brandName; }
  get cliName():   string { return this.domain.tenant.cliName; }
  get tenantSlug(): string { return this.domain.tenant.slug; }
  get version(): string { return this.domain.version; }

  // ── Operations ──────────────────────────────────────────────────────────────

  getOperations(): Array<{ id: string; op: Operation }> {
    return Object.entries(this.domain.operations).map(([id, op]) => ({ id, op }));
  }

  getOperation(id: string): Operation | undefined {
    return this.domain.operations[id];
  }

  searchOperations(query: string): Array<{ id: string; op: Operation }> {
    const q = query.toLowerCase();
    return this.getOperations().filter(
      ({ id, op }) =>
        id.includes(q) ||
        op.label.toLowerCase().includes(q) ||
        op.controllers.some(c => c.toLowerCase().includes(q)) ||
        op.services.some(s => s.toLowerCase().includes(q))
    );
  }

  // ── Statuses ────────────────────────────────────────────────────────────────

  getStatuses(): Array<{ code: string; description: string }> {
    return Object.entries(this.domain.statuses)
      .map(([code, description]) => ({ code, description }))
      .sort((a, b) => parseInt(a.code) - parseInt(b.code));
  }

  getStatus(code: string): string | undefined {
    return this.domain.statuses[code];
  }

  // ── Scan Rules ──────────────────────────────────────────────────────────────

  getScanRules(severity?: string, category?: string): Array<{ id: string; rule: ScanRule }> {
    return Object.entries(this.domain.scanRules)
      .filter(([_, rule]) =>
        (!severity || rule.severity === severity) &&
        (!category || rule.category === category)
      )
      .map(([id, rule]) => ({ id, rule }));
  }

  // ── Glossary ────────────────────────────────────────────────────────────────

  getGlossary(): Array<{ id: string; term: GlossaryTerm }> {
    return Object.entries(this.domain.glossary).map(([id, term]) => ({ id, term }));
  }

  searchGlossary(query: string): Array<{ id: string; term: GlossaryTerm }> {
    const q = query.toLowerCase();
    return this.getGlossary().filter(
      ({ id, term }) =>
        id.includes(q) ||
        term.label.toLowerCase().includes(q) ||
        term.definition.toLowerCase().includes(q)
    );
  }

  // ── Queues ──────────────────────────────────────────────────────────────────

  getQueues(): Array<{ id: string; label: string; consumer: string; description: string }> {
    return Object.entries(this.domain.queues).map(([id, q]) => ({ id, ...q }));
  }

  // ── Portals ─────────────────────────────────────────────────────────────────

  getPortals(): Array<{ id: string; name: string; path: string; products: string[] }> {
    return Object.entries(this.domain.portals).map(([id, p]) => ({ id, ...p }));
  }

  // ── DB ─────────────────────────────────────────────────────────────────

//   getDbs(): Array<{ id: string; name: string; path: string; products: string[] }> {
//     return Object.entries(this.domain.database).map(([id, p]) => ({ id, ...p }));
//   }

  // ── Raw domain access (for React islands) ───────────────────────────────────

  getRawDomain(): TenantDomain {
    return this.domain;
  }
}