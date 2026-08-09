import { ApplicationConfig, CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { provideHttpClient, withFetch } from '@angular/common/http';
import { provideZonelessChangeDetection } from '@angular/core';

import { routes } from './routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZonelessChangeDetection(),
    provideRouter(routes, withComponentInputBinding()),
    provideHttpClient(withFetch()),
  ],
};

/**
 * CUSTOM_ELEMENTS_SCHEMA is re-exported here for feature components
 * that host React islands via Custom Element tags.
 */
export { CUSTOM_ELEMENTS_SCHEMA };
