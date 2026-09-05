import type { ReactNode } from "react";

import type { AuthSession } from "../auth/AuthContext";
import { AuthContext } from "../auth/AuthContext";
import type { FrontendConfig } from "../config/env";

export const TEST_TOKEN = "eci-test-access-token-value";

export const TEST_ENV = {
  VITE_ECI_API_BASE_URL: "http://localhost:8000",
  VITE_ENTRA_AUTHORITY: "https://example.ciamlogin.com/11111111-1111-1111-1111-111111111111",
  VITE_ENTRA_SPA_CLIENT_ID: "22222222-2222-2222-2222-222222222222",
  VITE_ENTRA_REDIRECT_URI: "http://localhost:5173",
  VITE_ECI_API_SCOPES: [
    "api://33333333-3333-3333-3333-333333333333/communications:read",
    "api://33333333-3333-3333-3333-333333333333/communications:analyze",
    "api://33333333-3333-3333-3333-333333333333/communications:connect",
    "api://33333333-3333-3333-3333-333333333333/communications:workflow",
    "api://33333333-3333-3333-3333-333333333333/communications:send",
  ].join(","),
};

export const TEST_CONFIG: FrontendConfig = {
  apiBaseUrl: "http://localhost:8000",
  entraSpaClientId: "22222222-2222-2222-2222-222222222222",
  entraRedirectUri: "http://localhost:5173",
  eciApiScopes: TEST_ENV.VITE_ECI_API_SCOPES.split(","),
  entraAuthority: "https://example.ciamlogin.com/11111111-1111-1111-1111-111111111111",
  knownAuthorities: ["example.ciamlogin.com"],
};

export function createAuthSession(overrides: Partial<AuthSession> = {}): AuthSession {
  return {
    isAuthenticated: false,
    displayName: null,
    login: async () => undefined,
    logout: async () => undefined,
    error: null,
    interactionInProgress: false,
    permissions: ["communications:read", "communications:connect"],
    ...overrides,
  };
}

export function AuthStub({
  session,
  children,
}: {
  session: AuthSession;
  children: ReactNode;
}) {
  return <AuthContext.Provider value={session}>{children}</AuthContext.Provider>;
}
