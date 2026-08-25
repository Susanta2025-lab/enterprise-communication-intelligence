import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import { EciApiClient } from "../api/client";
import type { ConnectorAccount } from "../api/connectorAccounts";
import { connectorAccountMessageAnalyzePath } from "../api/mailbox";
import type { EciPermission } from "../auth/permissions";
import { formatMailboxTimestamp } from "../lib/formatTimestamp";
import { mailboxWorkspacePath } from "../navigation/paths";
import { AuthStub, TEST_TOKEN, createAuthSession } from "./fixtures";

const GMAIL_ID = "11111111-1111-4111-8111-111111111111";
const OPAQUE_CURSOR = "opaque/cursor+token=";
const MESSAGE_ID_ONE = "provider-msg-one-secret";
const MESSAGE_ID_TWO = "provider-msg-two-secret";
const ANALYSIS_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const ANALYSIS_ID_TWO = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const SUMMARY_TEXT = "The sender requested a quarterly review.";
const SUMMARY_TEXT_TWO = "Compiler notes require a follow-up.";
const DRAFT_BODY = "Thank you for the review request. I will follow up shortly.";
const ACTION_TEXT = "Prepare the quarterly review packet";
const ACTION_OWNER = "ada@example.com";
const ACTION_DUE_AT = "2026-08-29T17:00:00Z";
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

function analysisBody(overrides: Record<string, unknown> = {}) {
  return {
    analysis: {
      summary: { text: SUMMARY_TEXT },
      priority: { level: "high", rationale: "Action-oriented language." },
      category: "request",
      action_items: [
        {
          description: ACTION_TEXT,
          owner: ACTION_OWNER,
          due_at: ACTION_DUE_AT,
          priority: "high",
        },
      ],
      draft_reply: { body: DRAFT_BODY, tone: "neutral" },
      message_id: MESSAGE_ID_ONE,
    },
    provider: "mock",
    analysis_id: ANALYSIS_ID,
    ...overrides,
  };
}

function analyzeCalls(fetchImpl: ReturnType<typeof vi.fn<typeof fetch>>) {
  return fetchImpl.mock.calls.filter(([url]) => String(url).includes("/messages/analyze"));
}

function listMessageCalls(fetchImpl: ReturnType<typeof vi.fn<typeof fetch>>) {
  return fetchImpl.mock.calls.filter(([url]) => {
    const value = String(url);
    return value.includes("/messages") && !value.includes("/analyze");
  });
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
        permissions: options.permissions ?? ["communications:read", "communications:analyze"],
      })}
    >
      <App apiClient={apiClient} />
    </AuthStub>,
  );
}

async function selectAndAnalyze(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: /Ada Lovelace/ }));
  await user.click(screen.getByRole("button", { name: "Analyze message" }));
}

afterEach(() => {
  window.history.replaceState(null, "", "/");
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("analyze trigger", () => {
  it("does not analyze until the user clicks Analyze, and then posts once", async () => {
    const user = userEvent.setup();
    let release: ((value: Response) => void) | undefined;
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages/analyze")) {
        return new Promise<Response>((resolve) => {
          release = resolve;
        });
      }
      if (url.includes("/messages")) {
        return jsonResponse(200, { items: [messageItem()], next_cursor: null });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    expect(await screen.findByRole("button", { name: /Ada Lovelace/ })).toBeInTheDocument();
    expect(analyzeCalls(fetchImpl)).toHaveLength(0);
    expect(screen.queryByRole("button", { name: "Analyze message" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Ada Lovelace/ }));
    expect(analyzeCalls(fetchImpl)).toHaveLength(0);
    const analyzeButton = screen.getByRole("button", { name: "Analyze message" });
    expect(analyzeButton).toBeEnabled();
    await user.click(analyzeButton);
    expect(await screen.findByTestId("analysis-loading")).toHaveTextContent("Analyzing message");
    expect(screen.getByRole("button", { name: "Analyze message" })).toBeDisabled();
    expect(analyzeCalls(fetchImpl)).toHaveLength(1);
    const requested = new URL(String(analyzeCalls(fetchImpl)[0]?.[0]));
    expect(requested.pathname).toBe(connectorAccountMessageAnalyzePath(GMAIL_ID));
    expect(analyzeCalls(fetchImpl)[0]?.[1]).toEqual(
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ provider_message_id: MESSAGE_ID_ONE }),
      }),
    );

    release?.(jsonResponse(200, analysisBody()));
    expect(await screen.findByRole("heading", { name: "AI Analysis" })).toBeInTheDocument();
    expect(analyzeCalls(fetchImpl)).toHaveLength(1);
  });

  it("does not analyze on mailbox open, pagination, or refresh", async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages/analyze")) {
        return jsonResponse(200, analysisBody());
      }
      if (url.includes("/messages")) {
        const requested = new URL(url);
        if (requested.searchParams.get("cursor") === OPAQUE_CURSOR) {
          return jsonResponse(200, {
            items: [messageItem({ provider_message_id: MESSAGE_ID_TWO, sender: "Grace Hopper" })],
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
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(listMessageCalls(fetchImpl).length).toBeGreaterThanOrEqual(3));
    expect(analyzeCalls(fetchImpl)).toHaveLength(0);
  });

  it("does not issue an analyze request without communications:analyze", async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages")) {
        return jsonResponse(200, { items: [messageItem()], next_cursor: null });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl, permissions: ["communications:read"] });
    await user.click(await screen.findByRole("button", { name: /Ada Lovelace/ }));
    expect(screen.getByRole("button", { name: "Analyze message" })).toBeDisabled();
    expect(screen.getByText(/communications:analyze permission/)).toBeInTheDocument();
    expect(analyzeCalls(fetchImpl)).toHaveLength(0);
  });
});

describe("analysis result", () => {
  it("renders summary, priority, category, action items, and a read-only draft suggestion", async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages/analyze")) {
        return jsonResponse(200, analysisBody());
      }
      if (url.includes("/messages")) {
        return jsonResponse(200, { items: [messageItem()], next_cursor: null });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);

    const panel = await screen.findByRole("article", { name: "AI Analysis" });
    expect(within(panel).getByText(SUMMARY_TEXT)).toBeInTheDocument();
    expect(within(panel).getByText("High")).toBeInTheDocument();
    expect(within(panel).getByText("Action-oriented language.")).toBeInTheDocument();
    expect(within(panel).getByText("Request")).toBeInTheDocument();
    const actionList = within(panel).getByRole("list", { name: "Action items" });
    expect(within(actionList).getByText(ACTION_TEXT)).toBeInTheDocument();
    expect(within(actionList).getByText(`Owner: ${ACTION_OWNER}`)).toBeInTheDocument();
    expect(
      within(actionList).getByText(`Due: ${formatMailboxTimestamp(ACTION_DUE_AT)}`),
    ).toBeInTheDocument();
    expect(within(panel).getByRole("heading", { name: "AI draft suggestion" })).toBeInTheDocument();
    expect(within(panel).getByText(DRAFT_BODY)).toBeInTheDocument();
    expect(within(panel).getByText(/Not approved or sent/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /send|approve|propose|reject|execute/i })).toBeNull();
    expect(document.body.textContent).not.toContain(MESSAGE_ID_ONE);
    expect(document.body.textContent).not.toContain(ANALYSIS_ID);
    expect(screen.queryByText("mock")).not.toBeInTheDocument();
    expect(screen.queryByText(/MockAI/i)).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/raw body|message body/i);
    expect(screen.getByRole("button", { name: "Re-analyze message" })).toBeEnabled();
  });

  it("shows a neutral empty state when no action items are returned", async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages/analyze")) {
        return jsonResponse(
          200,
          analysisBody({
            analysis: {
              summary: { text: SUMMARY_TEXT },
              priority: { level: "medium" },
              category: "general",
              action_items: [],
              draft_reply: { body: DRAFT_BODY },
            },
          }),
        );
      }
      if (url.includes("/messages")) {
        return jsonResponse(200, { items: [messageItem()], next_cursor: null });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    expect(await screen.findByText("No action items identified.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("selection and refresh boundaries", () => {
  it("clears analysis when the selected message changes", async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages/analyze")) {
        return jsonResponse(200, analysisBody());
      }
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
    await selectAndAnalyze(user);
    expect(await screen.findByText(SUMMARY_TEXT)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Grace Hopper/ }));
    expect(screen.queryByText(SUMMARY_TEXT)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyze message" })).toBeEnabled();
    expect(analyzeCalls(fetchImpl)).toHaveLength(1);
  });

  it("clears analysis on mailbox refresh even when the selected message remains", async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages/analyze")) {
        return jsonResponse(200, analysisBody());
      }
      if (url.includes("/messages")) {
        return jsonResponse(200, { items: [messageItem()], next_cursor: null });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    expect(await screen.findByText(SUMMARY_TEXT)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => {
      expect(screen.queryByText(SUMMARY_TEXT)).not.toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Analyze message" })).toBeInTheDocument();
    expect(analyzeCalls(fetchImpl)).toHaveLength(1);
  });
});

describe("re-analysis", () => {
  it("keeps the previous result visible while re-analyzing and replaces it on success", async () => {
    const user = userEvent.setup();
    let analyzeCount = 0;
    let releaseSecond: ((value: Response) => void) | undefined;
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages/analyze")) {
        analyzeCount += 1;
        if (analyzeCount === 1) {
          return jsonResponse(200, analysisBody());
        }
        return new Promise<Response>((resolve) => {
          releaseSecond = resolve;
        });
      }
      if (url.includes("/messages")) {
        return jsonResponse(200, { items: [messageItem()], next_cursor: null });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    expect(await screen.findByText(SUMMARY_TEXT)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Re-analyze message" }));
    expect(screen.getByRole("status")).toHaveTextContent("Analyzing again…");
    expect(screen.getByText(SUMMARY_TEXT)).toBeInTheDocument();
    expect(analyzeCalls(fetchImpl)).toHaveLength(2);

    releaseSecond?.(
      jsonResponse(
        200,
        analysisBody({
          analysis: {
            summary: { text: SUMMARY_TEXT_TWO },
            priority: { level: "medium" },
            category: "inquiry",
            action_items: [],
            draft_reply: { body: DRAFT_BODY },
          },
          analysis_id: ANALYSIS_ID_TWO,
        }),
      ),
    );
    expect(await screen.findByText(SUMMARY_TEXT_TWO)).toBeInTheDocument();
    expect(screen.queryByText(SUMMARY_TEXT)).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain(ANALYSIS_ID_TWO);
  });

  it("preserves the previous success when re-analysis fails", async () => {
    const user = userEvent.setup();
    let analyzeCount = 0;
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages/analyze")) {
        analyzeCount += 1;
        if (analyzeCount === 1) {
          return jsonResponse(200, analysisBody());
        }
        return jsonResponse(500, { detail: "model timeout" });
      }
      if (url.includes("/messages")) {
        return jsonResponse(200, { items: [messageItem()], next_cursor: null });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    expect(await screen.findByText(SUMMARY_TEXT)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Re-analyze message" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The message could not be analyzed.");
    expect(screen.getByText(SUMMARY_TEXT)).toBeInTheDocument();
    expect(screen.queryByText("model timeout")).not.toBeInTheDocument();
    expect(analyzeCalls(fetchImpl)).toHaveLength(2);
  });

  it("does not automatically retry a failed analysis", async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages/analyze")) {
        return jsonResponse(503, { detail: "provider timeout" });
      }
      if (url.includes("/messages")) {
        return jsonResponse(200, { items: [messageItem()], next_cursor: null });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("temporarily unavailable");
    await new Promise((resolve) => setTimeout(resolve, 40));
    expect(analyzeCalls(fetchImpl)).toHaveLength(1);
  });
});

describe("analyze errors", () => {
  it("shows a safe 403 when analyze is forbidden by the API", async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages/analyze")) {
        return jsonResponse(403, { detail: "missing scope" });
      }
      if (url.includes("/messages")) {
        return jsonResponse(200, { items: [messageItem()], next_cursor: null });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("missing a required permission");
    expect(screen.queryByText("missing scope")).not.toBeInTheDocument();
  });

  it("guides the user to refresh the mailbox after a 404 message", async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages/analyze")) {
        return jsonResponse(404, { detail: "Mailbox message not found." });
      }
      if (url.includes("/messages")) {
        return jsonResponse(200, { items: [messageItem()], next_cursor: null });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("This message is no longer available");
    expect(screen.queryByText("Mailbox message not found.")).not.toBeInTheDocument();
    const listCountBefore = listMessageCalls(fetchImpl).length;
    await user.click(screen.getByRole("button", { name: "Refresh mailbox" }));
    await waitFor(() => expect(listMessageCalls(fetchImpl).length).toBeGreaterThan(listCountBefore));
    expect(analyzeCalls(fetchImpl)).toHaveLength(1);
  });

  it("invalidates connector state on 409 and does not retry analyze", async () => {
    const user = userEvent.setup();
    let status = "active";
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages/analyze")) {
        status = "reauth_required";
        return jsonResponse(409, { detail: "Connected mailbox is not available." });
      }
      if (url.includes("/messages")) {
        return jsonResponse(200, { items: [messageItem()], next_cursor: null });
      }
      return jsonResponse(200, listBody([account({ status })]));
    });
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    expect(await screen.findByTestId("mailbox-unavailable")).toHaveTextContent(
      "Reauthorization required",
    );
    expect(connectorCalls(fetchImpl).length).toBeGreaterThanOrEqual(2);
    expect(analyzeCalls(fetchImpl)).toHaveLength(1);
    expect(screen.queryByText("Connected mailbox is not available.")).not.toBeInTheDocument();
  });

  it("offers a manual retry after 503 without inventing REAUTH_REQUIRED", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages/analyze")) {
        attempts += 1;
        if (attempts === 1) {
          return jsonResponse(503, { detail: "provider timeout" });
        }
        return jsonResponse(200, analysisBody());
      }
      if (url.includes("/messages")) {
        return jsonResponse(200, { items: [messageItem()], next_cursor: null });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("temporarily unavailable");
    expect(screen.queryByText("provider timeout")).not.toBeInTheDocument();
    expect(screen.queryByTestId("mailbox-unavailable")).not.toBeInTheDocument();
    expect(connectorCalls(fetchImpl)).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText(SUMMARY_TEXT)).toBeInTheDocument();
    expect(analyzeCalls(fetchImpl)).toHaveLength(2);
    expect(screen.queryByText("Reauthorization required")).not.toBeInTheDocument();
  });

  it("shows a generic safe error for 500", async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages/analyze")) {
        return jsonResponse(500, { detail: "foundry stack trace" });
      }
      if (url.includes("/messages")) {
        return jsonResponse(200, { items: [messageItem()], next_cursor: null });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("The message could not be analyzed.");
    expect(screen.queryByText("foundry stack trace")).not.toBeInTheDocument();
  });

  it.each([
    [400, "The analysis request could not be completed.", "malformed body"],
    [401, "Sign in again", TEST_TOKEN],
    [422, "The analysis request could not be validated.", "invalid payload"],
  ] as const)("shows a safe message for HTTP %s without raw backend text", async (status, copy, detail) => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages/analyze")) {
        return jsonResponse(status, { detail });
      }
      if (url.includes("/messages")) {
        return jsonResponse(200, { items: [messageItem()], next_cursor: null });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    expect(await screen.findByRole("alert")).toHaveTextContent(copy);
    expect(screen.queryByText(detail)).not.toBeInTheDocument();
  });
});

describe("analysis privacy and accessibility", () => {
  it("keeps analysis content in memory and does not log or persist it", async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages/analyze")) {
        return jsonResponse(200, analysisBody());
      }
      if (url.includes("/messages")) {
        return jsonResponse(200, { items: [messageItem()], next_cursor: null });
      }
      return jsonResponse(200, listBody([account()]));
    });
    const logs = ["info", "log", "debug", "warn", "error"] as const;
    const spies = logs.map((method) => vi.spyOn(console, method).mockImplementation(() => undefined));
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    expect(await screen.findByText(SUMMARY_TEXT)).toBeInTheDocument();
    expect(window.localStorage.length).toBe(0);
    expect(window.location.href).not.toContain(SUMMARY_TEXT);
    expect(window.location.href).not.toContain(ANALYSIS_ID);
    expect(window.location.href).not.toContain(MESSAGE_ID_ONE);
    expect(window.location.pathname).toBe(mailboxWorkspacePath(GMAIL_ID));
    expect(fetchImpl.mock.calls.every(([url]) => !String(url).includes("workflow"))).toBe(true);
    expect(fetchImpl.mock.calls.every(([url]) => !String(url).includes("/communications/analyze"))).toBe(
      true,
    );
    const serialized = spies.map((spy) => JSON.stringify(spy.mock.calls)).join("");
    expect(serialized).not.toContain(SUMMARY_TEXT);
    expect(serialized).not.toContain(DRAFT_BODY);
    expect(serialized).not.toContain(MESSAGE_ID_ONE);
    expect(serialized).not.toContain(ANALYSIS_ID);
    spies.forEach((spy) => spy.mockRestore());
  });

  it("exposes accessible names, loading status, and an error alert", async () => {
    const user = userEvent.setup();
    let analyzeCount = 0;
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/messages/analyze")) {
        analyzeCount += 1;
        if (analyzeCount === 1) {
          return jsonResponse(500, { detail: "boom" });
        }
        return jsonResponse(200, analysisBody());
      }
      if (url.includes("/messages")) {
        return jsonResponse(200, { items: [messageItem()], next_cursor: null });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: /Ada Lovelace/ }));
    expect(screen.getByRole("button", { name: "Analyze message" })).toHaveAccessibleName(
      "Analyze message",
    );
    await user.click(screen.getByRole("button", { name: "Analyze message" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "AI Analysis" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Re-analyze message" })).toHaveAccessibleName(
      "Re-analyze message",
    );
    expect(screen.getByRole("heading", { name: "AI draft suggestion" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Action items" })).toBeInTheDocument();
    expect(screen.getByText("High")).toBeInTheDocument();
  });
});
