import {
  BrowserCacheLocation,
  PublicClientApplication,
  type Configuration,
  type IPublicClientApplication,
  type RedirectRequest,
} from "@azure/msal-browser";

import type { FrontendConfig } from "../config/env";

export function createMsalConfiguration(config: FrontendConfig): Configuration {
  return {
    auth: {
      clientId: config.entraSpaClientId,
      authority: config.entraAuthority,
      redirectUri: config.entraRedirectUri,
      postLogoutRedirectUri: config.entraRedirectUri,
    },
    cache: {
      cacheLocation: BrowserCacheLocation.SessionStorage,
    },
    system: {
      allowRedirectInIframe: false,
    },
  };
}

export function createMsalInstance(config: FrontendConfig): PublicClientApplication {
  return new PublicClientApplication(createMsalConfiguration(config));
}

export function buildLoginRequest(config: FrontendConfig): RedirectRequest {
  return {
    scopes: [...config.eciApiScopes],
    redirectUri: config.entraRedirectUri,
  };
}

export async function initializeMsal(instance: IPublicClientApplication): Promise<void> {
  await instance.initialize();
  const redirectResult = await instance.handleRedirectPromise();
  const account =
    redirectResult?.account ?? instance.getActiveAccount() ?? instance.getAllAccounts()[0] ?? null;
  if (account) {
    instance.setActiveAccount(account);
  }
}
