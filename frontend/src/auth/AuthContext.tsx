import { createContext, useContext } from "react";

import type { EciPermission } from "./permissions";

export type AuthSession = {
  isAuthenticated: boolean;
  displayName: string | null;
  login: () => Promise<void>;
  logout: () => Promise<void>;
  error: string | null;
  interactionInProgress: boolean;
  permissions: readonly EciPermission[];
};

export const AuthContext = createContext<AuthSession | null>(null);

export function useAuth(): AuthSession {
  const session = useContext(AuthContext);
  if (session === null) {
    throw new Error("useAuth must be used within an authentication provider.");
  }
  return session;
}
