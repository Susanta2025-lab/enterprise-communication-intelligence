import { InteractionStatus, type IPublicClientApplication } from "@azure/msal-browser";
import { MsalProvider, useIsAuthenticated, useMsal } from "@azure/msal-react";
import { useCallback, useMemo, useState, type ReactNode } from "react";

import type { FrontendConfig } from "../config/env";
import { AuthContext } from "./AuthContext";
import { buildLoginRequest } from "./msal";

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
  const interactionInProgress = inProgress !== InteractionStatus.None;

  const account = instance.getActiveAccount() ?? instance.getAllAccounts()[0] ?? null;
  const displayName = account?.name?.trim() || account?.username?.trim() || null;

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
    }),
    [displayName, error, interactionInProgress, isAuthenticated, login, logout],
  );

  return <AuthContext.Provider value={session}>{children}</AuthContext.Provider>;
}
