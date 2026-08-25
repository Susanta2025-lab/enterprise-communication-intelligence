import { InteractionStatus, type IPublicClientApplication } from "@azure/msal-browser";
import { MsalProvider, useIsAuthenticated, useMsal } from "@azure/msal-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import type { FrontendConfig } from "../config/env";
import { permissionsFromAccessToken } from "./accessTokenClaims";
import { AuthContext } from "./AuthContext";
import { buildLoginRequest } from "./msal";
import type { EciPermission } from "./permissions";

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

  const account = instance.getActiveAccount() ?? instance.getAllAccounts()[0] ?? null;
  const displayName = account?.name?.trim() || account?.username?.trim() || null;

  useEffect(() => {
    if (!isAuthenticated || account === null) {
      setPermissions([]);
      return;
    }
    let cancelled = false;
    void instance
      .acquireTokenSilent({
        account,
        scopes: [...config.eciApiScopes],
      })
      .then((result) => {
        if (cancelled || !result.accessToken) {
          return;
        }
        setPermissions(permissionsFromAccessToken(result.accessToken));
      })
      .catch(() => {
        if (!cancelled) {
          setPermissions([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [account, config.eciApiScopes, instance, isAuthenticated]);

  const login = useCallback(async () => {
    if (interactionInProgress) {
      return;
    }
    setError(null);
    try {
      await instance.loginRedirect(buildLoginRequest(config));
    } catch {
      setError("Sign-in could not be started. Try again.");
    }
  }, [config, instance, interactionInProgress]);

  const logout = useCallback(async () => {
    if (interactionInProgress) {
      return;
    }
    setError(null);
    try {
      await instance.logoutRedirect({
        account: account ?? undefined,
        postLogoutRedirectUri: config.entraRedirectUri,
      });
    } catch {
      setError("Sign-out could not be started. Try again.");
    }
  }, [account, config.entraRedirectUri, instance, interactionInProgress]);

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
