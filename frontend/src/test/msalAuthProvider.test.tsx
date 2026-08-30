import { InteractionStatus, type AccountInfo, type AuthenticationResult, type IPublicClientApplication } from "@azure/msal-browser";
import { render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAuth } from "../auth/AuthContext";
import { MsalAuthProvider } from "../auth/MsalAuthProvider";
import { TEST_CONFIG } from "./fixtures";

const msalHarness = vi.hoisted(() => ({
  instance: null as IPublicClientApplication | null,
  authenticated: true,
}));

vi.mock("@azure/msal-react", () => ({
  MsalProvider: ({ children }: { children: unknown }) => children,
  useMsal: () => ({
    instance: msalHarness.instance as IPublicClientApplication,
    inProgress: InteractionStatus.None,
    accounts: [],
  }),
  useIsAuthenticated: () => msalHarness.authenticated,
}));

const HOME_ACCOUNT_ID = "home-account-1";

function tokenWithPayload(payload: Record<string, unknown>): string {
  const json = btoa(JSON.stringify(payload)).replaceAll("=", "").replaceAll("+", "-").replaceAll("/", "_");
  return `header.${json}.sig`;
}

const SCOPED_TOKEN = tokenWithPayload({
  scp: "communications:read communications:analyze communications:connect",
});

function freshAccount(homeAccountId: string): AccountInfo {
  return {
    homeAccountId,
    localAccountId: "local-account-1",
    environment: "login.windows.net",
    tenantId: TEST_CONFIG.entraTenantId,
    username: "ada@example.com",
    name: "Ada Lovelace",
  };
}

function PermissionsProbe() {
  const { permissions } = useAuth();
  return <div data-testid="permissions">{permissions.join(" ")}</div>;
}

function createInstance(
  acquireTokenSilent: IPublicClientApplication["acquireTokenSilent"],
  homeAccountId: string | null = HOME_ACCOUNT_ID,
): IPublicClientApplication {
  return {
    getActiveAccount: vi.fn(() => (homeAccountId === null ? null : freshAccount(homeAccountId))),
    getAllAccounts: vi.fn(() => (homeAccountId === null ? [] : [freshAccount(homeAccountId)])),
    acquireTokenSilent,
  } as unknown as IPublicClientApplication;
}

function renderProvider(instance: IPublicClientApplication, wrapStrict = false) {
  msalHarness.instance = instance;
  const tree = (
    <MsalAuthProvider config={TEST_CONFIG} instance={instance}>
      <PermissionsProbe />
    </MsalAuthProvider>
  );
  return render(wrapStrict ? <StrictMode>{tree}</StrictMode> : tree);
}

describe("MsalAuthProvider silent-token effect", () => {
  beforeEach(() => {
    msalHarness.authenticated = true;
    msalHarness.instance = null;
  });

  afterEach(() => {
    msalHarness.authenticated = true;
    msalHarness.instance = null;
  });

  it("populates permissions once when AccountInfo identity changes every call", async () => {
    const acquireTokenSilent = vi.fn(async () => ({ accessToken: SCOPED_TOKEN }) as AuthenticationResult);
    const instance = createInstance(acquireTokenSilent);
    const { rerender } = renderProvider(instance);

    await waitFor(() => {
      expect(screen.getByTestId("permissions")).toHaveTextContent(
        "communications:read communications:analyze communications:connect",
      );
    });

    expect(acquireTokenSilent).toHaveBeenCalledTimes(1);

    rerender(
      <MsalAuthProvider config={TEST_CONFIG} instance={instance}>
        <PermissionsProbe />
      </MsalAuthProvider>,
    );
    await Promise.resolve();
    await Promise.resolve();

    expect(acquireTokenSilent).toHaveBeenCalledTimes(1);
    expect(instance.getActiveAccount).toHaveBeenCalled();
    const firstSilentRequest = acquireTokenSilent.mock.calls.at(0)?.at(0);
    expect(firstSilentRequest).toEqual(
      expect.objectContaining({
        account: expect.objectContaining({ homeAccountId: HOME_ACCOUNT_ID }),
        scopes: [...TEST_CONFIG.eciApiScopes],
      }),
    );
  });

  it("does not loop under StrictMode when AccountInfo objects are unstable", async () => {
    const acquireTokenSilent = vi.fn(async () => ({ accessToken: SCOPED_TOKEN }) as AuthenticationResult);
    const instance = createInstance(acquireTokenSilent);
    renderProvider(instance, true);

    await waitFor(() => {
      expect(screen.getByTestId("permissions")).toHaveTextContent("communications:read");
    });

    const callsAfterSettle = acquireTokenSilent.mock.calls.length;
    expect(callsAfterSettle).toBeLessThanOrEqual(2);
    await Promise.resolve();
    await Promise.resolve();
    expect(acquireTokenSilent.mock.calls.length).toBe(callsAfterSettle);
  });

  it("does not acquire a token or loop when already-empty permissions are cleared", async () => {
    msalHarness.authenticated = false;
    const acquireTokenSilent = vi.fn(async () => ({ accessToken: SCOPED_TOKEN }) as AuthenticationResult);
    const instance = createInstance(acquireTokenSilent, null);
    const { rerender } = renderProvider(instance);

    expect(screen.getByTestId("permissions")).toHaveTextContent("");
    expect(acquireTokenSilent).not.toHaveBeenCalled();

    rerender(
      <MsalAuthProvider config={TEST_CONFIG} instance={instance}>
        <PermissionsProbe />
      </MsalAuthProvider>,
    );
    await Promise.resolve();

    expect(acquireTokenSilent).not.toHaveBeenCalled();
    expect(screen.getByTestId("permissions")).toHaveTextContent("");
  });

  it("acquires again only when the stable account identifier changes", async () => {
    const acquireTokenSilent = vi.fn(async () => ({ accessToken: SCOPED_TOKEN }) as AuthenticationResult);
    const instance = createInstance(acquireTokenSilent, HOME_ACCOUNT_ID);
    const { rerender } = renderProvider(instance);

    await waitFor(() => {
      expect(screen.getByTestId("permissions")).toHaveTextContent("communications:connect");
    });
    expect(acquireTokenSilent).toHaveBeenCalledTimes(1);
    const afterFirst = acquireTokenSilent.mock.calls.length;

    vi.mocked(instance.getActiveAccount).mockImplementation(() => freshAccount("home-account-2"));
    vi.mocked(instance.getAllAccounts).mockImplementation(() => [freshAccount("home-account-2")]);
    rerender(
      <MsalAuthProvider config={TEST_CONFIG} instance={instance}>
        <PermissionsProbe />
      </MsalAuthProvider>,
    );

    await waitFor(() => {
      expect(acquireTokenSilent).toHaveBeenCalledTimes(afterFirst + 1);
    });
    const switchedRequest = acquireTokenSilent.mock.calls.at(-1)?.at(0);
    expect(switchedRequest).toEqual(
      expect.objectContaining({
        account: expect.objectContaining({ homeAccountId: "home-account-2" }),
      }),
    );
  });
});
