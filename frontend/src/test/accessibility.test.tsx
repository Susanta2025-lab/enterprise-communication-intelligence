import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { axe } from "jest-axe";

import { App } from "../App";
import { EciApiClient } from "../api/client";
import { ConnectorStatus } from "../components/connectors/ConnectorStatus";
import { PriorityBadge } from "../components/mailbox/PriorityBadge";
import { WorkflowStatusBadge } from "../components/mailbox/WorkflowStatusBadge";
import { ExecutionUncertainState } from "../components/mailbox/ExecutionUncertainState";
import { mailboxWorkspacePath } from "../navigation/paths";
import { AuthStub, TEST_TOKEN, createAuthSession } from "./fixtures";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("accessible status semantics", () => {
  it("exposes connector lifecycle as readable text", () => {
    const { rerender } = render(<ConnectorStatus status="active" />);
    expect(screen.getByTestId("connector-status")).toHaveTextContent("Active — mailbox available");
    rerender(<ConnectorStatus status="reauth_required" />);
    expect(screen.getByTestId("connector-status")).toHaveTextContent("Reauthorization required");
    expect(screen.getByText(/was not deleted/i)).toBeInTheDocument();
    rerender(<ConnectorStatus status="disconnected" />);
    expect(screen.getByTestId("connector-status")).toHaveTextContent("Disconnected");
  });

  it("exposes priority and workflow status as readable text", () => {
    render(
      <>
        <PriorityBadge level="critical" />
        <WorkflowStatusBadge status="pending" />
        <WorkflowStatusBadge status="executed" />
        <ExecutionUncertainState />
      </>,
    );
    expect(screen.getByText("Critical")).toBeInTheDocument();
    expect(screen.getByText("Pending review")).toBeInTheDocument();
    expect(screen.getByText("Reply sent")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Sending status is uncertain.");
    expect(screen.queryByText(/retry send/i)).not.toBeInTheDocument();
  });
});

describe("authentication and dashboard landmarks", () => {
  it("exposes a main landmark while signed out and header plus main while signed in", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () =>
      jsonResponse(200, { items: [], limit: 20, offset: 0 }),
    );
    const apiClient = new EciApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: { acquireAccessToken: async () => TEST_TOKEN },
      fetchImpl,
    });
    const { rerender } = render(
      <AuthStub session={createAuthSession({ isAuthenticated: false })}>
        <App apiClient={apiClient} />
      </AuthStub>,
    );
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();

    rerender(
      <AuthStub
        session={createAuthSession({
          isAuthenticated: true,
          displayName: "Ada Lovelace",
          permissions: ["communications:read", "communications:connect"],
        })}
      >
        <App apiClient={apiClient} />
      </AuthStub>,
    );
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Connected mailboxes" })).toBeInTheDocument();
    expect(screen.getByTestId("connector-loading")).toHaveTextContent("Loading connector accounts");
  });
});

describe("automated accessibility checks", () => {
  it("has no axe violations on the signed-out shell", async () => {
    const apiClient = new EciApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: { acquireAccessToken: async () => TEST_TOKEN },
      fetchImpl: vi.fn<typeof fetch>(),
    });
    const { container } = render(
      <AuthStub session={createAuthSession({ isAuthenticated: false })}>
        <App apiClient={apiClient} />
      </AuthStub>,
    );
    const results = await axe(container);
    expect(results.violations).toEqual([]);
  });

  it("has no axe violations on connector lifecycle status", async () => {
    const { container } = render(
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <ConnectorStatus status="reauth_required" />
        </QueryClientProvider>
      </MemoryRouter>,
    );
    const results = await axe(container);
    expect(results.violations).toEqual([]);
  });
});

describe("mailbox selection accessibility", () => {
  it("marks the selected message for assistive technology", async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages")) {
        return jsonResponse(200, {
          items: [
            {
              provider_message_id: "provider-msg-one-secret",
              sender: "Ada Lovelace",
              subject: "Quarterly review",
              sent_at: "2026-08-25T15:30:00Z",
              received_at: "2026-08-25T15:31:00Z",
            },
          ],
          next_cursor: null,
        });
      }
      return jsonResponse(200, {
        items: [
          {
            id: "11111111-1111-4111-8111-111111111111",
            provider: "gmail",
            status: "active",
            granted_capabilities: ["mail.read"],
            created_at: "2026-08-25T00:00:00Z",
            updated_at: "2026-08-25T00:00:00Z",
          },
        ],
        limit: 20,
        offset: 0,
      });
    });
    window.history.replaceState(
      null,
      "",
      mailboxWorkspacePath("11111111-1111-4111-8111-111111111111"),
    );
    const apiClient = new EciApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: { acquireAccessToken: async () => TEST_TOKEN },
      fetchImpl,
    });
    render(
      <AuthStub
        session={createAuthSession({
          isAuthenticated: true,
          displayName: "Ada Lovelace",
          permissions: ["communications:read"],
        })}
      >
        <App apiClient={apiClient} />
      </AuthStub>,
    );
    const row = await screen.findByRole("button", { name: /Ada Lovelace/ });
    expect(row).toHaveAttribute("aria-pressed", "false");
    row.focus();
    await user.keyboard("{Enter}");
    expect(row).toHaveAttribute("aria-pressed", "true");
    expect(row).toHaveTextContent("Selected");
    expect(screen.getByRole("navigation", { name: "Mailbox" })).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("provider-msg-one-secret");
  });
});
