import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EciApiClient } from "../api/client";
import {
  CONNECTOR_ACCOUNTS_PATH,
  GMAIL_AUTHORIZE_PATH,
  MICROSOFT_GRAPH_AUTHORIZE_PATH,
} from "../api/errors";
import type { ConnectorAccount } from "../api/connectorAccounts";
import type { EciPermission } from "../auth/permissions";
import { ConnectorDashboardPage } from "../pages/ConnectorDashboardPage";
import { AuthStub, TEST_TOKEN, createAuthSession } from "./fixtures";

const { assignBrowserLocation } = vi.hoisted(() => ({
  assignBrowserLocation: vi.fn(),
}));

vi.mock("../navigation/external", () => ({
  assignBrowserLocation,
  isSafeAuthorizationUrl: (value: string) => {
    try {
      const parsed = new URL(value);
      return parsed.protocol === "https:" && !parsed.username && !parsed.password && Boolean(parsed.hostname);
    } catch {
      return false;
    }
  },
  navigateToAuthorizationUrl: (url: string) => {
    try {
      const parsed = new URL(url);
      if (parsed.protocol !== "https:" || parsed.username || parsed.password || !parsed.hostname) {
        return false;
      }
    } catch {
      return false;
    }
    assignBrowserLocation(url);
    return true;
  },
}));

const GMAIL_ID = "11111111-1111-4111-8111-111111111111";
const GMAIL_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth?client_id=test";
const GRAPH_AUTH_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?client_id=test";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function account(overrides: Partial<ConnectorAccount> = {}): ConnectorAccount {
  return {
    id: GMAIL_ID,
    provider: "gmail",
    status: "active",
    granted_capabilities: ["mail.read", "mail.send"],
    created_at: "2026-08-25T00:00:00Z",
    updated_at: "2026-08-25T00:00:00Z",
    ...overrides,
  };
}

function listBody(items: ConnectorAccount[]) {
  return { items, limit: 20, offset: 0 };
}

function renderDashboard(options: {
  fetchImpl: ReturnType<typeof vi.fn<typeof fetch>>;
  permissions?: readonly EciPermission[];
  search?: string;
}) {
  if (options.search !== undefined) {
    window.history.replaceState(null, "", `/${options.search}`);
  } else {
    window.history.replaceState(null, "", "/");
  }
  const apiClient = new EciApiClient({
    baseUrl: "http://localhost:8000",
    tokenProvider: { acquireAccessToken: async () => TEST_TOKEN },
    fetchImpl: options.fetchImpl,
  });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <AuthStub
      session={createAuthSession({
        isAuthenticated: true,
        displayName: "Ada Lovelace",
        permissions: options.permissions ?? ["communications:read", "communications:connect"],
      })}
    >
      <QueryClientProvider client={queryClient}>
        <ConnectorDashboardPage apiClient={apiClient} />
      </QueryClientProvider>
    </AuthStub>,
  );
  return { apiClient, queryClient };
}

afterEach(() => {
  window.history.replaceState(null, "", "/");
  assignBrowserLocation.mockClear();
});

describe("connector dashboard", () => {
  it("shows a labelled loading state then empty connect actions", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => jsonResponse(200, listBody([])));
    renderDashboard({ fetchImpl });
    expect(screen.getByRole("status")).toHaveTextContent("Loading connector accounts");
    expect(await screen.findByRole("button", { name: "Connect Gmail" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect Microsoft Outlook" })).toBeInTheDocument();
    expect(fetchImpl).toHaveBeenCalledWith(
      expect.stringContaining(CONNECTOR_ACCOUNTS_PATH),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: `Bearer ${TEST_TOKEN}` }),
      }),
    );
  });

  it("renders ACTIVE account capabilities without internal identifiers", async () => {
    const fetchImpl = vi.fn<typeof fetch>(
      async () => jsonResponse(200, listBody([account({ id: GMAIL_ID, status: "active" })])),
    );
    renderDashboard({ fetchImpl });
    expect(await screen.findByRole("heading", { name: "Gmail" })).toBeInTheDocument();
    expect(screen.getByTestId("connector-status")).toHaveTextContent("Active — mailbox available");
    expect(screen.getByText("mail.read")).toBeInTheDocument();
    expect(screen.getByText("mail.send")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disconnect" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Connect Gmail" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect Microsoft Outlook" })).toBeInTheDocument();
    expect(document.body.textContent).not.toContain(GMAIL_ID);
    expect(document.body.textContent).not.toContain("credential_ref");
    expect(document.body.textContent).not.toContain("external_account_id");
  });

  it("renders REAUTH_REQUIRED with reconnect and does not imply deletion", async () => {
    const fetchImpl = vi.fn<typeof fetch>(
      async () =>
        jsonResponse(
          200,
          listBody([account({ id: GMAIL_ID, status: "reauth_required", granted_capabilities: ["mail.read"] })]),
        ),
    );
    renderDashboard({ fetchImpl });
    expect(await screen.findByText("Reauthorization required")).toBeInTheDocument();
    expect(screen.getByText(/was not deleted/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reconnect" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disconnect" })).toBeInTheDocument();
  });

  it("renders DISCONNECTED with reconnect", async () => {
    const fetchImpl = vi.fn<typeof fetch>(
      async () =>
        jsonResponse(
          200,
          listBody([
            account({
              id: GMAIL_ID,
              status: "disconnected",
              granted_capabilities: null,
            }),
          ]),
        ),
    );
    renderDashboard({ fetchImpl });
    expect(await screen.findByText("Disconnected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reconnect" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Connect Gmail" })).not.toBeInTheDocument();
  });

  it("hides lifecycle actions without communications:connect", async () => {
    const fetchImpl = vi.fn<typeof fetch>(
      async () => jsonResponse(200, listBody([account({ status: "active" })])),
    );
    renderDashboard({ fetchImpl, permissions: ["communications:read"] });
    expect(await screen.findByRole("heading", { name: "Gmail" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Disconnect" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Connect Microsoft Outlook" })).not.toBeInTheDocument();
    expect(screen.getAllByText(/communications:connect permission/i).length).toBeGreaterThan(0);
  });

  it("shows product-safe copy for 401, 403, 409, and 503", async () => {
    for (const [status, copy] of [
      [401, "Sign in again"],
      [403, "missing a required permission"],
      [409, "cannot be updated right now"],
      [503, "temporarily unavailable"],
    ] as const) {
      const fetchImpl = vi.fn<typeof fetch>(async () => jsonResponse(status, { detail: "raw provider boom" }));
      const { unmount } = render(
        <AuthStub session={createAuthSession({ isAuthenticated: true })}>
          <QueryClientProvider
            client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
          >
            <ConnectorDashboardPage
              apiClient={
                new EciApiClient({
                  baseUrl: "http://localhost:8000",
                  tokenProvider: { acquireAccessToken: async () => TEST_TOKEN },
                  fetchImpl,
                })
              }
            />
          </QueryClientProvider>
        </AuthStub>,
      );
      expect(await screen.findByRole("alert")).toHaveTextContent(copy);
      expect(screen.queryByText("raw provider boom")).not.toBeInTheDocument();
      unmount();
    }
  });

  it("manual refresh re-requests the connector list", async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn<typeof fetch>(async () => jsonResponse(200, listBody([])));
    renderDashboard({ fetchImpl });
    await screen.findByRole("button", { name: "Connect Gmail" });
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(fetchImpl.mock.calls.length).toBeGreaterThanOrEqual(2));
    expect(fetchImpl.mock.calls.every(([url]) => String(url).includes(CONNECTOR_ACCOUNTS_PATH))).toBe(
      true,
    );
  });
});

describe("connector oauth actions", () => {
  it("starts Gmail connect and navigates to the returned authorization URL", async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes(GMAIL_AUTHORIZE_PATH) && !url.includes("gmail/authorize/")) {
        return jsonResponse(200, { authorization_url: GMAIL_AUTH_URL, expires_at: "2026-08-25T00:10:00Z" });
      }
      return jsonResponse(200, listBody([]));
    });
    renderDashboard({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: "Connect Gmail" }));
    await waitFor(() => expect(assignBrowserLocation).toHaveBeenCalledWith(GMAIL_AUTH_URL));
    expect(fetchImpl.mock.calls.some(([url]) => String(url).includes(GMAIL_AUTHORIZE_PATH))).toBe(true);
  });

  it("starts Microsoft connect and navigates to the returned authorization URL", async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes(MICROSOFT_GRAPH_AUTHORIZE_PATH)) {
        return jsonResponse(200, { authorization_url: GRAPH_AUTH_URL, expires_at: "2026-08-25T00:10:00Z" });
      }
      return jsonResponse(200, listBody([]));
    });
    renderDashboard({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: "Connect Microsoft Outlook" }));
    await waitFor(() => expect(assignBrowserLocation).toHaveBeenCalledWith(GRAPH_AUTH_URL));
  });

  it("reauthorizes the exact REAUTH_REQUIRED connector", async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes(`/${GMAIL_ID}/reauthorize`)) {
        return jsonResponse(200, { authorization_url: GMAIL_AUTH_URL, expires_at: "2026-08-25T00:10:00Z" });
      }
      return jsonResponse(200, listBody([account({ id: GMAIL_ID, status: "reauth_required" })]));
    });
    renderDashboard({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: "Reconnect" }));
    await waitFor(() => expect(assignBrowserLocation).toHaveBeenCalledWith(GMAIL_AUTH_URL));
    expect(fetchImpl.mock.calls.some(([url]) => String(url).includes(`/${GMAIL_ID}/reauthorize`))).toBe(
      true,
    );
  });

  it("requires disconnect confirmation and refreshes after success", async () => {
    const user = userEvent.setup();
    let disconnected = false;
    const fetchImpl = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url.includes(`/${GMAIL_ID}/disconnect`) && init && init.method === "POST") {
        disconnected = true;
        return jsonResponse(200, {
          id: GMAIL_ID,
          provider: "gmail",
          status: "disconnected",
          granted_capabilities: null,
          created_at: "2026-08-25T00:00:00Z",
          updated_at: "2026-08-25T00:01:00Z",
        });
      }
      if (disconnected) {
        return jsonResponse(
          200,
          listBody([account({ id: GMAIL_ID, status: "disconnected", granted_capabilities: null })]),
        );
      }
      return jsonResponse(200, listBody([account({ id: GMAIL_ID, status: "active" })]));
    });
    renderDashboard({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: "Disconnect" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/removes ECI's active mailbox authorization/i)).toBeInTheDocument();
    expect(fetchImpl.mock.calls.some(([url]) => String(url).includes("/disconnect"))).toBe(false);
    await user.click(within(dialog).getByRole("button", { name: "Disconnect" }));
    expect(await screen.findByText("Disconnected")).toBeInTheDocument();
    expect(fetchImpl.mock.calls.some(([url]) => String(url).includes(`/${GMAIL_ID}/disconnect`))).toBe(
      true,
    );
  });

  it("does not disconnect when confirmation is cancelled", async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn<typeof fetch>(
      async () => jsonResponse(200, listBody([account({ status: "active" })])),
    );
    renderDashboard({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: "Disconnect" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(fetchImpl.mock.calls.some(([url]) => String(url).includes("/disconnect"))).toBe(false);
    expect(screen.getByTestId("connector-status")).toHaveTextContent("Active — mailbox available");
  });

  it("does not pretend success when disconnect fails", async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url.includes("/disconnect") && init && init.method === "POST") {
        return jsonResponse(503, { detail: "store down" });
      }
      return jsonResponse(200, listBody([account({ status: "active" })]));
    });
    renderDashboard({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: "Disconnect" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Disconnect" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("temporarily unavailable");
    expect(screen.getByTestId("connector-status")).toHaveTextContent("Active — mailbox available");
    expect(screen.queryByText("store down")).not.toBeInTheDocument();
  });
});

describe("oauth return handling", () => {
  it.each([
    ["?oauth=success&provider=gmail", "Mailbox connected"],
    ["?oauth=denied&provider=gmail", "consent was not completed"],
    ["?oauth=expired&provider=gmail", "authorization session expired"],
    ["?oauth=identity_mismatch&provider=gmail", "same mailbox account"],
    ["?oauth=failed&provider=gmail", "Mailbox connection failed"],
    ["?oauth=weird&provider=gmail", "Mailbox connection status is unavailable"],
  ] as const)("handles %s", async (search, copy) => {
    const fetchImpl = vi.fn<typeof fetch>(async () => jsonResponse(200, listBody([])));
    renderDashboard({ fetchImpl, search });
    expect(await screen.findByTestId("oauth-return-notice")).toHaveTextContent(copy);
    expect(window.location.search).toBe("");
    expect(document.body.textContent).not.toContain("weird");
    expect(document.body.textContent).not.toContain("error_description");
  });

  it("loads connector accounts after success and strips query values", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => jsonResponse(200, listBody([])));
    renderDashboard({ fetchImpl, search: "?oauth=success&provider=microsoft_graph" });
    expect(await screen.findByTestId("oauth-return-notice")).toHaveTextContent("Mailbox connected");
    await waitFor(() => expect(fetchImpl).toHaveBeenCalled());
    expect(fetchImpl.mock.calls[0]?.[0]).toEqual(expect.stringContaining(CONNECTOR_ACCOUNTS_PATH));
    expect(window.location.search).toBe("");
  });
});
