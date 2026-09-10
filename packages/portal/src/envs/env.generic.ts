// import { TENANT_DOMAIN as MSI_DOMAIN } from '@onboarded/shared/tenants/msi';
import { TENANT_DOMAIN as GENERIC_DOMAIN } from '../types/lib/tenants/generic';

export const environment = {
  production: false,
  tenant: 'generic',
  tenantDomain: GENERIC_DOMAIN,
  apiBase: 'http://localhost:8000',
};
