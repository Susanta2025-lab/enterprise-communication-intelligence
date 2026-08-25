import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import { EciApiClient } from "../api/client";
import type { ConnectorAccount } from "../api/connectorAccounts";
import { MAILBOX_UI_PAGE_SIZE } from "../api/mailbox";
import { formatMailboxTimestamp } from "../lib/formatTimestamp";
import { mailboxWorkspacePath } from "../navigation/paths";
import type { EciPermission } from "../auth/permissions";
import { AuthStub, TEST_TOKEN, createAuthSession } from "./fixtures";

const GMAIL_ID = "11111111-1111-4111-8111-111111111111";
const OPAQUE_CURSOR = "opaque/cursor+token=";
const MESSAGE_ID_ONE = "provider-msg-one-secret";
const MESSAGE_ID_TWO = "provider-msg-two-secret";
const SENT_AT = "2026-08-25T15:30:00Z";
const RECEIVED_AT = "2026-08-25T15:31:00Z";

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

function messageItem(overrides: Record<string, unknown> = {}) {
  return {
    provider_message_id: MESSAGE_ID_ONE,
    sender: "Ada Lovelace",
    subject: "Quarterly review",
    sent_at: SENT_AT,
    received_at: RECEIVED_AT,
    ...overrides,
  };
}

function messageCalls(fetchImpl: ReturnType<typeof vi.fn<typeof fetch>>) {
  return fetchImpl.mock.calls.filter(([url]) => String(url).includes("/messages"));
}

function connectorCalls(fetchImpl: ReturnType<typeof vi.fn<typeof fetch>>) {
  return fetchImpl.mock.calls.filter(([url]) => {
    const value = String(url);
    return value.includes("/connector-accounts") && !value.includes("/messages");
  });
}

function renderWorkspace(options: {
  fetchImpl: ReturnType<typeof vi.fn<typeof fetch>>;
  permissions?: readonly EciPermission[];
  path?: string;
}) {
  window.history.replaceState(null, "", options.path ?? mailboxWorkspacePath(GMAIL_ID));
  const apiClient = new EciApiClient({
    baseUrl: "http://localhost:8000",
    tokenProvider: { acquireAccessToken: async () => TEST_TOKEN },
    fetchImpl: options.fetchImpl,
  });
  render(
    <AuthStub
      session={createAuthSession({
        isAuthenticated: true,
        displayName: "Ada Lovelace",
        permissions: options.permissions ?? ["communications:read", "communications:connect"],
      })}
    >
      <App apiClient={apiClient} />
    </AuthStub>,
  );
  return { apiClient };
}

afterEach(() => {
  window.history.replaceState(null, "", "/");
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("mailbox workspace entry", () => {
  it("opens the workspace from an ACTIVE connector and loads the first page", async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages")) {
        return jsonResponse(200, { items: [messageItem()], next_cursor: null });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl, path: "/" });
    expect(await screen.findByRole("heading", { name: "Gmail" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open mailbox" }));
    expect(await screen.findByRole("heading", { name: "Gmail mailbox" })).toBeInTheDocument();
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("Quarterly review")).toBeInTheDocument();
    expect(window.location.pathname).toBe(mailboxWorkspacePath(GMAIL_ID));
    const requested = new URL(String(messageCalls(fetchImpl)[0]?.[0]));
    expect(requested.searchParams.get("page_size")).toBe(String(MAILBOX_UI_PAGE_SIZE));
    expect(requested.searchParams.has("cursor")).toBe(false);
  });

  it("shows a mailbox loading skeleton before the first page arrives", async () => {
    let release: ((value: Response) => void) | undefined;
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages")) {
        return new Promise<Response>((resolve) => {
          release = resolve;
        });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    expect(await screen.findByTestId("mailbox-loading")).toHaveTextContent("Loading mailbox messages");
    release?.(jsonResponse(200, { items: [messageItem()], next_cursor: null }));
    expect(await screen.findByRole("button", { name: /Ada Lovelace/ })).toBeInTheDocument();
  });

  it("does not fetch mailbox messages for REAUTH_REQUIRED connectors", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () =>
      jsonResponse(200, listBody([account({ status: "reauth_required" })])),
    );
    renderWorkspace({ fetchImpl });
    expect(await screen.findByTestId("mailbox-unavailable")).toHaveTextContent("Reauthorization required");
    expect(messageCalls(fetchImpl)).toHaveLength(0);
    expect(screen.getAllByRole("link", { name: "Back to dashboard" }).length).toBeGreaterThan(0);
  });

  it("does not fetch mailbox messages for DISCONNECTED connectors", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () =>
      jsonResponse(200, listBody([account({ status: "disconnected", granted_capabilities: null })])),
    );
    renderWorkspace({ fetchImpl });
    expect(await screen.findByTestId("mailbox-unavailable")).toHaveTextContent("Mailbox disconnected");
    expect(messageCalls(fetchImpl)).toHaveLength(0);
  });
});

describe("mailbox list rendering", () => {
  it("renders sender, subject, and timestamps without provider identifiers", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages")) {
        return jsonResponse(200, { items: [messageItem()], next_cursor: null });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    const row = await screen.findByRole("button", { name: /Ada Lovelace/ });
    expect(row).toHaveTextContent("Quarterly review");
    expect(row).toHaveTextContent(formatMailboxTimestamp(RECEIVED_AT) ?? "missing");
    expect(document.body.textContent).not.toContain(MESSAGE_ID_ONE);
    expect(document.body.textContent).not.toContain(GMAIL_ID);
    expect(document.body.textContent).not.toContain("2026-08-25T15:31:00Z");
  });

  it("shows product copy when subject is absent", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages")) {
        return jsonResponse(200, {
          items: [messageItem({ subject: null })],
          next_cursor: null,
        });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    expect(await screen.findByText("(No subject)")).toBeInTheDocument();
  });

  it("shows a neutral empty state when the page has no items", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages")) {
        return jsonResponse(200, { items: [], next_cursor: null });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    expect(await screen.findByTestId("mailbox-empty")).toHaveTextContent(
      "No recent messages were returned.",
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("selects one message and shows metadata without calling analyze or detail APIs", async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages")) {
        return jsonResponse(200, {
          items: [
            messageItem(),
            messageItem({
              provider_message_id: MESSAGE_ID_TWO,
              sender: "Grace Hopper",
              subject: "Compiler notes",
            }),
          ],
          next_cursor: null,
        });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    const first = await screen.findByRole("button", { name: /Ada Lovelace/ });
    first.focus();
    await user.keyboard("{Enter}");
    expect(first).toHaveAttribute("aria-pressed", "true");
    const panel = screen.getByRole("complementary", { name: "Selected message" });
    expect(within(panel).getByText("Ada Lovelace")).toBeInTheDocument();
    expect(within(panel).getByText("Quarterly review")).toBeInTheDocument();
    expect(within(panel).getByText("Gmail")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyze message" })).toBeDisabled();
    expect(screen.getByText(/communications:analyze permission/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain(MESSAGE_ID_ONE);
    expect(messageCalls(fetchImpl).every(([url]) => !String(url).includes("/analyze"))).toBe(true);
    expect(fetchImpl.mock.calls.every(([url]) => !String(url).includes("workflow"))).toBe(true);
  });
});

describe("mailbox pagination", () => {
  it("shows Load more only when next_cursor is present and appends the next page", async () => {
    const user = userEvent.setup();
    let secondPagePending: ((value: Response) => void) | undefined;
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages")) {
        const requested = new URL(url);
        if (requested.searchParams.get("cursor") === OPAQUE_CURSOR) {
          return new Promise<Response>((resolve) => {
            secondPagePending = resolve;
          });
        }
        return jsonResponse(200, {
          items: [messageItem()],
          next_cursor: OPAQUE_CURSOR,
        });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    expect(await screen.findByRole("button", { name: "Load more" })).toBeInTheDocument();
    expect(document.body.textContent).not.toContain(OPAQUE_CURSOR);
    expect(window.location.search).toBe("");
    expect(window.location.href).not.toContain(OPAQUE_CURSOR);

    await user.click(screen.getByRole("button", { name: "Load more" }));
    expect(screen.getByRole("button", { name: /Ada Lovelace/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Loading more" })).toBeDisabled();
    expect(new URL(String(messageCalls(fetchImpl)[1]?.[0])).searchParams.get("cursor")).toBe(
      OPAQUE_CURSOR,
    );

    secondPagePending?.(
      jsonResponse(200, {
        items: [messageItem({ provider_message_id: MESSAGE_ID_TWO, sender: "Grace Hopper" })],
        next_cursor: null,
      }),
    );
    expect(await screen.findByRole("button", { name: /Grace Hopper/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Ada Lovelace/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
    expect(messageCalls(fetchImpl)).toHaveLength(2);
  });

  it("does not prefetch additional pages", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages")) {
        return jsonResponse(200, { items: [messageItem()], next_cursor: OPAQUE_CURSOR });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    await screen.findByRole("button", { name: "Load more" });
    await new Promise((resolve) => setTimeout(resolve, 40));
    expect(messageCalls(fetchImpl)).toHaveLength(1);
  });

  it("hides Load more when the first page has no next_cursor", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages")) {
        return jsonResponse(200, { items: [messageItem()], next_cursor: null });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    await screen.findByRole("button", { name: /Ada Lovelace/ });
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  it("does not render duplicate rows for the same provider message", async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages")) {
        const requested = new URL(url);
        if (requested.searchParams.get("cursor") === OPAQUE_CURSOR) {
          return jsonResponse(200, {
            items: [
              messageItem(),
              messageItem({ provider_message_id: MESSAGE_ID_TWO, sender: "Grace Hopper" }),
            ],
            next_cursor: null,
          });
        }
        return jsonResponse(200, { items: [messageItem()], next_cursor: OPAQUE_CURSOR });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: "Load more" }));
    expect(await screen.findByRole("button", { name: /Grace Hopper/ })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Ada Lovelace/ })).toHaveLength(1);
  });
});

describe("mailbox refresh and errors", () => {
  it("recovers from an invalid cursor by refreshing the first page", async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages")) {
        const requested = new URL(url);
        if (requested.searchParams.get("cursor") === OPAQUE_CURSOR) {
          return jsonResponse(400, { detail: OPAQUE_CURSOR });
        }
        return jsonResponse(200, { items: [messageItem()], next_cursor: OPAQUE_CURSOR });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: "Load more" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This mailbox page expired or is no longer valid.",
    );
    expect(screen.queryByText(OPAQUE_CURSOR)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Refresh mailbox" }));
    await waitFor(() => expect(messageCalls(fetchImpl).length).toBeGreaterThanOrEqual(3));
    const refreshed = new URL(String(messageCalls(fetchImpl).at(-1)?.[0]));
    expect(refreshed.searchParams.has("cursor")).toBe(false);
  });

  it("invalidates connector state on 409 and shows reauthorization UX", async () => {
    let status = "active";
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages")) {
        status = "reauth_required";
        return jsonResponse(409, { detail: "Connected mailbox is not available." });
      }
      return jsonResponse(200, listBody([account({ status })]));
    });
    renderWorkspace({ fetchImpl });
    expect(await screen.findByTestId("mailbox-unavailable")).toHaveTextContent("Reauthorization required");
    expect(connectorCalls(fetchImpl).length).toBeGreaterThanOrEqual(2);
    expect(messageCalls(fetchImpl)).toHaveLength(1);
    expect(screen.queryByText("Connected mailbox is not available.")).not.toBeInTheDocument();
  });

  it("offers a single manual retry after 503 and does not auto-retry", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages")) {
        attempts += 1;
        if (attempts === 1) {
          return jsonResponse(503, { detail: "provider timeout" });
        }
        return jsonResponse(200, { items: [messageItem()], next_cursor: null });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    expect(await screen.findByRole("alert")).toHaveTextContent("temporarily unavailable");
    expect(screen.queryByText("provider timeout")).not.toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 40));
    expect(messageCalls(fetchImpl)).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("button", { name: /Ada Lovelace/ })).toBeInTheDocument();
    expect(messageCalls(fetchImpl)).toHaveLength(2);
  });

  it("shows a safe unavailable state for 404", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => jsonResponse(200, listBody([])));
    renderWorkspace({ fetchImpl });
    expect(await screen.findByRole("alert")).toHaveTextContent("That mailbox connection is unavailable.");
    expect(messageCalls(fetchImpl)).toHaveLength(0);
    expect(screen.getAllByRole("link", { name: "Back to dashboard" }).length).toBeGreaterThan(0);
  });

  it("does not request mailbox data without communications:read", async () => {
    const fetchImpl = vi.fn<typeof fetch>();
    renderWorkspace({ fetchImpl, permissions: ["communications:connect"] });
    expect(await screen.findByRole("alert")).toHaveTextContent("communications:read");
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("shows authentication copy for 401", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages")) {
        return jsonResponse(401, { detail: TEST_TOKEN });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    expect(await screen.findByRole("alert")).toHaveTextContent("Sign in again");
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain(TEST_TOKEN);
  });

  it("shows permission copy for backend 403", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages")) {
        return jsonResponse(403, { detail: "missing scope" });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    expect(await screen.findByRole("alert")).toHaveTextContent("communications:read");
    expect(screen.queryByText("missing scope")).not.toBeInTheDocument();
  });

  it("resets the cursor chain on manual refresh and clears a missing selection", async () => {
    const user = userEvent.setup();
    let firstPageItems = [
      messageItem(),
      messageItem({ provider_message_id: MESSAGE_ID_TWO, sender: "Grace Hopper" }),
    ];
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages")) {
        const requested = new URL(url);
        if (requested.searchParams.get("cursor") === OPAQUE_CURSOR) {
          return jsonResponse(200, { items: [], next_cursor: null });
        }
        return jsonResponse(200, { items: firstPageItems, next_cursor: OPAQUE_CURSOR });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    const selected = await screen.findByRole("button", { name: /Grace Hopper/ });
    await user.click(selected);
    expect(selected).toHaveAttribute("aria-pressed", "true");
    firstPageItems = [messageItem()];
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /Grace Hopper/ })).not.toBeInTheDocument();
    });
    const lastMessages = new URL(String(messageCalls(fetchImpl).at(-1)?.[0]));
    expect(lastMessages.searchParams.has("cursor")).toBe(false);
    expect(
      screen.getByRole("complementary", { name: "Selected message" }),
    ).toHaveTextContent("Select a message to view its details.");
  });
});

describe("mailbox privacy boundary", () => {
  it("does not persist mailbox payloads or render credentials, cursors, or bodies", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages")) {
        return jsonResponse(200, {
          items: [messageItem()],
          next_cursor: OPAQUE_CURSOR,
        });
      }
      return jsonResponse(200, listBody([account()]));
    });
    const log = vi.spyOn(console, "info").mockImplementation(() => undefined);
    renderWorkspace({ fetchImpl });
    await screen.findByRole("button", { name: /Ada Lovelace/ });
    expect(document.body.textContent).not.toContain(MESSAGE_ID_ONE);
    expect(document.body.textContent).not.toContain(OPAQUE_CURSOR);
    expect(document.body.textContent).not.toContain("credential_ref");
    expect(document.body.textContent).not.toContain("https://mail.google.com");
    expect(document.body.textContent).not.toMatch(/raw body|message body/i);
    expect(window.localStorage.length).toBe(0);
    expect(JSON.stringify(log.mock.calls)).not.toContain(MESSAGE_ID_ONE);
    expect(JSON.stringify(log.mock.calls)).not.toContain(OPAQUE_CURSOR);
    log.mockRestore();
  });
});
