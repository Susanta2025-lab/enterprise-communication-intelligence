import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { App } from "../App";
import { EciApiClient } from "../api/client";
import { PROTECTED_ANALYSES_SMOKE_PATH } from "../api/errors";
import { AuthStub, TEST_TOKEN, createAuthSession } from "./fixtures";

function renderApp(options: {
  isAuthenticated: boolean;
  fetchImpl?: ReturnType<typeof vi.fn<typeof fetch>>;
  login?: () => Promise<void>;
  logout?: () => Promise<void>;
  error?: string | null;
}) {
  const fetchImpl =
    options.fetchImpl ??
    vi.fn<typeof fetch>(async () => {
      return new Response(JSON.stringify({ items: [], limit: 1, offset: 0 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
  const apiClient = new EciApiClient({
    baseUrl: "http://localhost:8000",
    tokenProvider: { acquireAccessToken: async () => TEST_TOKEN },
    fetchImpl,
  });
  const login = options.login ?? vi.fn(async () => undefined);
  const logout = options.logout ?? vi.fn(async () => undefined);

  render(
    <AuthStub
      session={createAuthSession({
        isAuthenticated: options.isAuthenticated,
        displayName: options.isAuthenticated ? "Ada Lovelace" : null,
        login,
        logout,
        error: options.error ?? null,
      })}
    >
      <App apiClient={apiClient} />
    </AuthStub>,
  );

  return { fetchImpl, login, logout };
}

describe("authentication shell", () => {
  it("renders an unauthenticated sign-in state", () => {
    const { fetchImpl } = renderApp({ isAuthenticated: false });
    expect(screen.getByRole("heading", { name: "ECI Platform" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Check API connection" })).not.toBeInTheDocument();
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("wires the sign-in action", async () => {
    const user = userEvent.setup();
    const { login } = renderApp({ isAuthenticated: false });
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(login).toHaveBeenCalledTimes(1);
  });

  it("renders the authenticated shell and wires sign-out", async () => {
    const user = userEvent.setup();
    const { fetchImpl, logout } = renderApp({ isAuthenticated: true });
    expect(screen.getByTestId("signed-in-account")).toHaveTextContent("Signed in as Ada Lovelace");
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
    expect(fetchImpl).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Sign out" }));
    expect(logout).toHaveBeenCalledTimes(1);
  });

  it("shows authentication errors without rendering tokens", () => {
    renderApp({ isAuthenticated: false, error: "Sign-in could not be started. Try again." });
    expect(screen.getByRole("alert")).toHaveTextContent("Sign-in could not be started. Try again.");
    expect(document.body.textContent).not.toContain(TEST_TOKEN);
  });
});

describe("protected API status panel", () => {
  it("does not issue a protected product request while unauthenticated", () => {
    const { fetchImpl } = renderApp({ isAuthenticated: false });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("calls GET /api/v1/analyses?limit=1 after an authenticated check", async () => {
    const user = userEvent.setup();
    const { fetchImpl } = renderApp({ isAuthenticated: true });
    await user.click(screen.getByRole("button", { name: "Check API connection" }));
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(fetchImpl).toHaveBeenCalledWith(
      expect.stringContaining(PROTECTED_ANALYSES_SMOKE_PATH),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: `Bearer ${TEST_TOKEN}`,
        }),
      }),
    );
    expect(await screen.findByTestId("api-status-message")).toHaveTextContent(
      "Protected API responded successfully.",
    );
    expect(document.body.textContent).not.toContain(TEST_TOKEN);
  });
});
