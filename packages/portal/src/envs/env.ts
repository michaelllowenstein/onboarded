import { TENANT_DOMAIN as MSI_DOMAIN } from '@onboarded/shared/tenants/msi';

export const environment = {
  production: false,
  tenant: 'msi',
  tenantDomain: MSI_DOMAIN,
  apiBase: 'http://localhost:8000',
};
