import {
  EventType,
  InteractionStatus,
  type AccountInfo,
  type EventMessage,
  type IPublicClientApplication,
} from "@azure/msal-browser";
import { MsalProvider, useIsAuthenticated, useMsal } from "@azure/msal-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import type { FrontendConfig } from "../config/env";
import { permissionsFromAccessToken } from "./accessTokenClaims";
import { AuthContext } from "./AuthContext";
import { resolveDisplayName } from "./displayName";
import { buildLoginRequest, buildLogoutRequest } from "./msal";
import { logMsalDiagError } from "./msalDiagnostics";
import type { EciPermission } from "./permissions";

const EMPTY_PERMISSIONS: readonly EciPermission[] = [];
const REDIRECT_FAILURE_MESSAGE = "Sign-in could not be completed. Try again.";

function resolveAccount(instance: IPublicClientApplication): AccountInfo | null {
  return instance.getActiveAccount() ?? instance.getAllAccounts()[0] ?? null;
}

function samePermissionList(
  left: readonly EciPermission[],
  right: readonly EciPermission[],
): boolean {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

function retainPermissionsIfUnchanged(
  next: readonly EciPermission[],
): (previous: readonly EciPermission[]) => readonly EciPermission[] {
  return (previous) => (samePermissionList(previous, next) ? previous : next);
}

type MsalAuthProviderProps = {
  config: FrontendConfig;
  instance: IPublicClientApplication;
  children: ReactNode;
};

export function MsalAuthProvider({ config, instance, children }: MsalAuthProviderProps) {
  return (
    <MsalProvider instance={instance}>
      <MsalAuthSession config={config}>{children}</MsalAuthSession>
    </MsalProvider>
  );
}

function MsalAuthSession({
  config,
  children,
}: {
  config: FrontendConfig;
  children: ReactNode;
}) {
  const { instance, inProgress } = useMsal();
  const isAuthenticated = useIsAuthenticated();
  const [error, setError] = useState<string | null>(null);
  const [permissions, setPermissions] = useState<readonly EciPermission[]>([]);
  const interactionInProgress = inProgress !== InteractionStatus.None;

  const account = resolveAccount(instance);
  const accountId = account?.homeAccountId ?? null;
  const displayName = resolveDisplayName(account);

  useEffect(() => {
    const callbackId = instance.addEventCallback((message: EventMessage) => {
      // MSAL browser v5 emits login/redirect failures as ACQUIRE_TOKEN_FAILURE
      // (LOGIN_FAILURE was removed).
      if (message.eventType !== EventType.ACQUIRE_TOKEN_FAILURE) {
        return;
      }
      logMsalDiagError("auth interaction failed", message.error, {
        eventType: message.eventType,
        interactionStatus: inProgress,
        accountCount: instance.getAllAccounts().length,
        hasActiveAccount: instance.getActiveAccount() !== null,
      });
      setError(REDIRECT_FAILURE_MESSAGE);
    });
    return () => {
      if (callbackId) {
        instance.removeEventCallback(callbackId);
      }
    };
  }, [inProgress, instance]);

  useEffect(() => {
    // Wait until MsalProvider finishes Startup / redirect handling before
    // touching tokens; interactive APIs must not race handleRedirectPromise.
    if (interactionInProgress || !isAuthenticated || accountId === null) {
      setPermissions(retainPermissionsIfUnchanged(EMPTY_PERMISSIONS));
      return;
    }
    const currentAccount = resolveAccount(instance);
    if (currentAccount === null || currentAccount.homeAccountId !== accountId) {
      setPermissions(retainPermissionsIfUnchanged(EMPTY_PERMISSIONS));
      return;
    }
    let cancelled = false;
    void instance
      .acquireTokenSilent({
        account: currentAccount,
        scopes: [...config.eciApiScopes],
      })
      .then((result) => {
        if (cancelled || !result.accessToken) {
          return;
        }
        setPermissions(retainPermissionsIfUnchanged(permissionsFromAccessToken(result.accessToken)));
      })
      .catch((error: unknown) => {
        logMsalDiagError("permission token acquire failed", error, {
          eventType: "acquireTokenSilent",
          accountCount: instance.getAllAccounts().length,
          hasActiveAccount: instance.getActiveAccount() !== null,
        });
        if (!cancelled) {
          setPermissions(retainPermissionsIfUnchanged(EMPTY_PERMISSIONS));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [accountId, config.eciApiScopes, instance, interactionInProgress, isAuthenticated]);

  const login = useCallback(async () => {
    if (interactionInProgress) {
      return;
    }
    setError(null);
    try {
      await instance.loginRedirect(buildLoginRequest(config));
    } catch (error: unknown) {
      logMsalDiagError("loginRedirect failed", error, {
        eventType: "loginRedirect",
        interactionStatus: inProgress,
      });
      setError("Sign-in could not be started. Try again.");
    }
  }, [config, inProgress, instance, interactionInProgress]);

  const logout = useCallback(async () => {
    if (interactionInProgress) {
      return;
    }
    setError(null);
    try {
      await instance.logoutRedirect(buildLogoutRequest(config, account));
    } catch {
      setError("Sign-out could not be started. Try again.");
    }
  }, [account, config, instance, interactionInProgress]);

  const session = useMemo(
    () => ({
      isAuthenticated,
      displayName,
      login,
      logout,
      error,
      interactionInProgress,
      permissions,
    }),
    [displayName, error, interactionInProgress, isAuthenticated, login, logout, permissions],
  );

  return <AuthContext.Provider value={session}>{children}</AuthContext.Provider>;
}
