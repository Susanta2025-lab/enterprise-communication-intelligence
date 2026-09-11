import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EciApiClient } from "../api/client";
import { ME_PATH, parseMeResponse } from "../api/me";
import { CurrentUserProvider } from "../auth/CurrentUserContext";
import { useCurrentUser } from "../auth/useCurrentUser";
import { PermissionGate } from "../components/connectors/PermissionGate";
import { AppShell } from "../components/AppShell";
import { AuthStub, TEST_TOKEN, createAuthSession } from "./fixtures";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function Probe() {
  const { status, applicationRole, isOwner } = useCurrentUser();
  return (
    <div>
      <span data-testid="me-status">{status}</span>
      <span data-testid="me-role">{applicationRole ?? "none"}</span>
      <span data-testid="me-owner">{isOwner ? "yes" : "no"}</span>
    </div>
  );
}

function renderCurrentUser(options: {
  isAuthenticated?: boolean;
  accountKey?: string | null;
  permissions?: readonly ("communications:read" | "communications:analyze" | "communications:connect" | "communications:workflow" | "communications:send")[];
  meResponse?: Response | (() => Promise<Response>);
  includeShell?: boolean;
}) {
  const fetchImpl = vi.fn<typeof fetch>(async (input) => {
    const url = String(input);
    if (url.includes(ME_PATH)) {
      if (typeof options.meResponse === "function") {
        return options.meResponse();
      }
      return (
        options.meResponse ??
        jsonResponse(200, { application_role: "user", is_owner: false })
      );
    }
    return jsonResponse(500, { detail: "unexpected" });
  });
  const apiClient = new EciApiClient({
    baseUrl: "http://localhost:8000",
    tokenProvider: { acquireAccessToken: async () => TEST_TOKEN },
    fetchImpl,
  });
  const session = createAuthSession({
    isAuthenticated: options.isAuthenticated ?? true,
    accountKey: options.accountKey === undefined ? "home-account-1" : options.accountKey,
    displayName: "Ada Lovelace",
    permissions: options.permissions ?? ["communications:read", "communications:connect"],
  });

  render(
    <AuthStub session={session}>
      <CurrentUserProvider apiClient={apiClient}>
        {options.includeShell ? <AppShell>content</AppShell> : <Probe />}
        <PermissionGate permission="communications:send">
          <span data-testid="send-gate">send-allowed</span>
        </PermissionGate>
      </CurrentUserProvider>
    </AuthStub>,
  );

  return { fetchImpl, apiClient };
}

describe("parseMeResponse", () => {
  it("accepts only consistent server payloads", () => {
    expect(parseMeResponse({ application_role: "user", is_owner: false })).toEqual({
      application_role: "user",
      is_owner: false,
    });
    expect(parseMeResponse({ application_role: "owner", is_owner: true })).toEqual({
      application_role: "owner",
      is_owner: true,
    });
    expect(parseMeResponse({ application_role: "owner", is_owner: false })).toBeNull();
    expect(parseMeResponse({ application_role: "user", is_owner: true })).toBeNull();
    expect(parseMeResponse({ roles: ["owner"], is_owner: true })).toBeNull();
  });
});

describe("CurrentUserProvider", () => {
  it("loads ordinary user state from /me", async () => {
    const { fetchImpl } = renderCurrentUser({});
    await waitFor(() => expect(screen.getByTestId("me-status")).toHaveTextContent("ready"));
    expect(screen.getByTestId("me-role")).toHaveTextContent("user");
    expect(screen.getByTestId("me-owner")).toHaveTextContent("no");
    expect(fetchImpl).toHaveBeenCalledWith(
      expect.stringContaining(ME_PATH),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: `Bearer ${TEST_TOKEN}`,
        }),
      }),
    );
  });

  it("loads owner state from successful /me only", async () => {
    renderCurrentUser({
      meResponse: jsonResponse(200, { application_role: "owner", is_owner: true }),
      includeShell: true,
    });
    expect(await screen.findByTestId("owner-badge")).toHaveTextContent("Platform Owner");
    expect(screen.getByTestId("signed-in-account")).toHaveTextContent("Ada Lovelace");
  });

  it("does not show owner badge for ordinary /me", async () => {
    renderCurrentUser({ includeShell: true });
    await waitFor(() =>
      expect(screen.getByTestId("signed-in-account")).toHaveTextContent("Ada Lovelace"),
    );
    expect(screen.queryByTestId("owner-badge")).not.toBeInTheDocument();
  });

  it("does not treat MSAL/JWT roles as owner without /me", async () => {
    const { fetchImpl } = renderCurrentUser({
      meResponse: jsonResponse(200, { application_role: "user", is_owner: false }),
    });
    await waitFor(() => expect(screen.getByTestId("me-owner")).toHaveTextContent("no"));
    expect(fetchImpl.mock.calls.every(([url]) => String(url).includes(ME_PATH))).toBe(true);
  });

  it("does not produce owner UI when /me fails", async () => {
    renderCurrentUser({
      meResponse: jsonResponse(503, { detail: "Persistence is currently unavailable." }),
      includeShell: true,
    });
    await waitFor(() => expect(screen.queryByTestId("owner-badge")).not.toBeInTheDocument());
  });

  it("does not produce owner UI when /me returns inconsistent payload", async () => {
    renderCurrentUser({
      meResponse: jsonResponse(200, { application_role: "owner", is_owner: false }),
      includeShell: true,
    });
    await waitFor(() => expect(screen.queryByTestId("owner-badge")).not.toBeInTheDocument());
  });

  it("clears owner state when unauthenticated", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () =>
      jsonResponse(200, { application_role: "owner", is_owner: true }),
    );
    const apiClient = new EciApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: { acquireAccessToken: async () => TEST_TOKEN },
      fetchImpl,
    });
    const { rerender } = render(
      <AuthStub
        session={createAuthSession({
          isAuthenticated: true,
          accountKey: "home-account-1",
          displayName: "Ada Lovelace",
        })}
      >
        <CurrentUserProvider apiClient={apiClient}>
          <Probe />
        </CurrentUserProvider>
      </AuthStub>,
    );

    await waitFor(() => expect(screen.getByTestId("me-owner")).toHaveTextContent("yes"));

    rerender(
      <AuthStub
        session={createAuthSession({
          isAuthenticated: false,
          accountKey: null,
          displayName: null,
        })}
      >
        <CurrentUserProvider apiClient={apiClient}>
          <Probe />
        </CurrentUserProvider>
      </AuthStub>,
    );

    await waitFor(() => expect(screen.getByTestId("me-status")).toHaveTextContent("anonymous"));
    expect(screen.getByTestId("me-owner")).toHaveTextContent("no");
  });

  it("does not leak previous owner state across account keys", async () => {
    let meBody = { application_role: "owner", is_owner: true };
    const fetchImpl = vi.fn<typeof fetch>(async () => jsonResponse(200, meBody));
    const apiClient = new EciApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: { acquireAccessToken: async () => TEST_TOKEN },
      fetchImpl,
    });

    const { rerender } = render(
      <AuthStub
        session={createAuthSession({
          isAuthenticated: true,
          accountKey: "owner-account",
          displayName: "Owner Person",
        })}
      >
        <CurrentUserProvider apiClient={apiClient}>
          <Probe />
        </CurrentUserProvider>
      </AuthStub>,
    );

    await waitFor(() => expect(screen.getByTestId("me-owner")).toHaveTextContent("yes"));

    meBody = { application_role: "user", is_owner: false };
    rerender(
      <AuthStub
        session={createAuthSession({
          isAuthenticated: true,
          accountKey: "other-account",
          displayName: "Ordinary Person",
        })}
      >
        <CurrentUserProvider apiClient={apiClient}>
          <Probe />
        </CurrentUserProvider>
      </AuthStub>,
    );

    await waitFor(() => expect(screen.getByTestId("me-owner")).toHaveTextContent("no"));
    expect(screen.getByTestId("me-role")).toHaveTextContent("user");
  });

  it("keeps PermissionGate independent of owner state", async () => {
    renderCurrentUser({
      meResponse: jsonResponse(200, { application_role: "owner", is_owner: true }),
      permissions: ["communications:read"],
    });
    await waitFor(() => expect(screen.getByTestId("me-owner")).toHaveTextContent("yes"));
    expect(screen.queryByTestId("send-gate")).not.toBeInTheDocument();
  });

  it("does not fetch /me while anonymous", () => {
    const { fetchImpl } = renderCurrentUser({
      isAuthenticated: false,
      accountKey: null,
    });
    expect(screen.getByTestId("me-status")).toHaveTextContent("anonymous");
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});
