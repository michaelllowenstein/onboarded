import { TENANT_DOMAIN as GENERIC_DOMAIN } from '@onboarded/shared/tenants/generic';

export const environment = {
  production: false,
  tenant: 'generic',
  tenantDomain: GENERIC_DOMAIN,
  apiBase: 'http://localhost:8000',
};
