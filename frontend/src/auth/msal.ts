import {
  BrowserCacheLocation,
  EventType,
  PublicClientApplication,
  type AccountInfo,
  type AuthenticationResult,
  type Configuration,
  type EndSessionRequest,
  type EventMessage,
  type IPublicClientApplication,
  type RedirectRequest,
} from "@azure/msal-browser";

import type { FrontendConfig } from "../config/env";
import { logMsalDiag, scanAuthRedirectLocation } from "./msalDiagnostics";

export function createMsalConfiguration(config: FrontendConfig): Configuration {
  return {
    auth: {
      clientId: config.entraSpaClientId,
      authority: config.entraAuthority,
      knownAuthorities: [...config.knownAuthorities],
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

function accountFromAuthEvent(message: EventMessage): AccountInfo | null {
  if (
    message.eventType !== EventType.LOGIN_SUCCESS &&
    message.eventType !== EventType.ACQUIRE_TOKEN_SUCCESS
  ) {
    return null;
  }
  const payload = message.payload;
  if (!payload || typeof payload !== "object") {
    return null;
  }
  if ("account" in payload) {
    return (payload as AuthenticationResult).account ?? null;
  }
  if ("homeAccountId" in payload) {
    return payload as AccountInfo;
  }
  return null;
}

export function createMsalInstance(config: FrontendConfig): PublicClientApplication {
  const instance = new PublicClientApplication(createMsalConfiguration(config));
  // msal-react v5 owns handleRedirectPromise inside MsalProvider. Keep active
  // account in sync when that redirect (or a later silent acquire) succeeds.
  instance.addEventCallback((message) => {
    const account = accountFromAuthEvent(message);
    if (account) {
      instance.setActiveAccount(account);
      logMsalDiag("active account promoted", {
        eventType: message.eventType,
        hasActiveAccount: true,
        accountCount: instance.getAllAccounts().length,
      });
    }
  });
  return instance;
}

export function buildLoginRequest(config: FrontendConfig): RedirectRequest {
  return {
    scopes: [...config.eciApiScopes],
    redirectUri: config.entraRedirectUri,
  };
}

export function buildLogoutRequest(
  config: FrontendConfig,
  account: AccountInfo | null,
): EndSessionRequest {
  return {
    account: account ?? undefined,
    postLogoutRedirectUri: config.entraRedirectUri,
  };
}

/**
 * Completes PCA initialize only. Do not call handleRedirectPromise here —
 * @azure/msal-react v5 MsalProvider performs redirect processing on mount.
 */
export async function initializeMsal(instance: IPublicClientApplication): Promise<void> {
  await instance.initialize();

  const locationScan = scanAuthRedirectLocation();
  logMsalDiag("initialize location scan", {
    hasAuthParamsInHash: locationScan.hasAuthParamsInHash,
    hasAuthParamsInQuery: locationScan.hasAuthParamsInQuery,
    accountCount: instance.getAllAccounts().length,
    hasActiveAccount: instance.getActiveAccount() !== null,
  });

  const account = instance.getActiveAccount() ?? instance.getAllAccounts()[0] ?? null;
  if (account) {
    instance.setActiveAccount(account);
  }
}
