// // tenant.types.ts — Onboarded shared TypeScript interfaces
// // Imported by: portal (at build time via TENANT_DOMAIN constant)
// //              api (at startup via domain_loader.py-generated dicts)
// //              admin-cli (for typed API client request/response models)

export type Severity = 'critical' | 'error' | 'warning' | 'info';
export type Category = 'security' | 'convention' | 'architecture' | 'dependency' | 'observability';

export interface RepoConfig {
  env: string;
  default: string;
}

export interface TenantMeta {
  slug: string;
  brandName: string;
  cliName: string;
  terminology: {
    operations: string;
    statuses: string;
    products: string;
    queues?: string;
    portals?: string;
  };
}

export interface Operation {
  label: string;
  controllers: string[];
  services: string[];
  queues: string[];
  js: string[];
  tables?: string[];
  clusters?: string[];
}

export interface ScanRule {
  label: string;
  pattern: string;
  severity: Severity;
  category: Category;
  scope: string[];
  repos: string[];
  exclude: string[];
  reference: string;
  fixHint: string;
}

export interface ScanFinding {
  ruleId: string;
  ruleName: string;
  severity: Severity;
  file: string;
  line: number;
  match: string;
  fixHint: string;
}

export interface GlossaryTerm {
  label: string;
  definition: string;
  seeAlso: string[];
}

/** MSI portal shape — matches packages/core/tenants/msi/domain.json */
export interface Portal {
  name: string;
  path: string;
  products: string[];
}

export interface Queue {
  label: string;
  consumer: string;
  description: string;
}

export interface Product {
  code?: number;
  label: string;
  controllers?: string[];
  gen3?: string[];
  js?: string[];
  webjobs?: string[];
}

/** Props passed from Angular ReactBridgeService into every React island */
export interface IslandProps {
  tenantSlug: string;
  apiBase: string;
  onNavigate?: (route: string) => void;
}
export interface TenantDomain {
  version: string;
  tenant: TenantMeta;
  operations: Record<string, Operation>;
  statuses: Record<string, string>;
  products: Record<string, Product>;
  portals: Record<string, Portal>;
  queues: Record<string, Queue>;
  glossary: Record<string, GlossaryTerm>;
  scanRules: Record<string, ScanRule>;
}