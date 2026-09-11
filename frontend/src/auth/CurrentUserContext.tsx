import { useEffect, useMemo, useState, type ReactNode } from "react";

import type { EciApiClient } from "../api/client";
import { useAuth } from "./AuthContext";
import {
  ANONYMOUS_CURRENT_USER,
  ERROR_CURRENT_USER,
  LOADING_CURRENT_USER,
  type CurrentUserState,
} from "./currentUserState";
import { CurrentUserContext } from "./useCurrentUser";

type CurrentUserProviderProps = {
  apiClient: EciApiClient;
  children: ReactNode;
};

/**
 * Fetches server-authoritative /me for presentation only.
 * Never grants authorization; /me failure never yields owner UI.
 */
export function CurrentUserProvider({ apiClient, children }: CurrentUserProviderProps) {
  const { isAuthenticated, accountKey } = useAuth();
  const [state, setState] = useState<CurrentUserState>(ANONYMOUS_CURRENT_USER);

  useEffect(() => {
    if (!isAuthenticated || accountKey === null) {
      setState(ANONYMOUS_CURRENT_USER);
      return;
    }

    let cancelled = false;
    setState(LOADING_CURRENT_USER);

    void apiClient
      .getMe()
      .then((me) => {
        if (cancelled) {
          return;
        }
        setState({
          status: "ready",
          applicationRole: me.application_role,
          isOwner: me.is_owner === true && me.application_role === "owner",
        });
      })
      .catch(() => {
        if (!cancelled) {
          setState(ERROR_CURRENT_USER);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [accountKey, apiClient, isAuthenticated]);

  const value = useMemo(() => state, [state]);

  return <CurrentUserContext.Provider value={value}>{children}</CurrentUserContext.Provider>;
}
