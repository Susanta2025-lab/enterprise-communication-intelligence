import { render, screen, waitFor, within, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import { EciApiClient } from "../api/client";
import type { ConnectorAccount } from "../api/connectorAccounts";
import type { WorkflowActionResponse, WorkflowActionStatus } from "../api/workflowActions";
import type { EciPermission } from "../auth/permissions";
import { mailboxWorkspacePath } from "../navigation/paths";
import { AuthStub, TEST_TOKEN, createAuthSession } from "./fixtures";

const GMAIL_ID = "11111111-1111-4111-8111-111111111111";
const MESSAGE_ID_ONE = "provider-msg-one-secret";
const MESSAGE_ID_TWO = "provider-msg-two-secret";
const ANALYSIS_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const ANALYSIS_ID_TWO = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const ACTION_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
const SUMMARY_TEXT = "The sender requested a quarterly review.";
const DRAFT_BODY = "Thank you for the review request. I will follow up shortly.";
const SNAPSHOT_BODY = "Proposed snapshot for analysis A. This is not the live draft.";
const NEW_DRAFT_BODY = "New draft after re-analysis.";
const SENT_AT = "2026-08-25T15:30:00Z";
const RECEIVED_AT = "2026-08-25T15:31:00Z";

const ALL_PERMISSIONS: readonly EciPermission[] = [
  "communications:read",
  "communications:analyze",
  "communications:workflow",
  "communications:send",
];

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
      priority: { level: "high" },
      category: "request",
      action_items: [],
      draft_reply: { body: DRAFT_BODY },
      message_id: MESSAGE_ID_ONE,
    },
    provider: "mock",
    analysis_id: ANALYSIS_ID,
    ...overrides,
  };
}

function workflowAction(overrides: Partial<WorkflowActionResponse> = {}): WorkflowActionResponse {
  return {
    id: ACTION_ID,
    action_type: "reply",
    analysis_id: ANALYSIS_ID,
    status: "pending",
    proposed_reply_body: SNAPSHOT_BODY,
    approved_reply_body: null,
    created_at: "2026-08-25T16:00:00Z",
    approved_at: null,
    rejected_at: null,
    executed_at: null,
    failed_at: null,
    has_execution_target: true,
    ...overrides,
  };
}

function pathnameOf(input: RequestInfo | URL): string {
  return new URL(String(input)).pathname;
}

function methodOf(init: RequestInit | undefined): string {
  return init?.method ?? "GET";
}

function isCreateWorkflow(input: RequestInfo | URL, init?: RequestInit): boolean {
  return pathnameOf(input) === "/api/v1/workflow-actions" && methodOf(init) === "POST";
}

function isGetWorkflow(input: RequestInfo | URL, init?: RequestInit): boolean {
  const path = pathnameOf(input);
  return methodOf(init) === "GET" && path.startsWith("/api/v1/workflow-actions/");
}

function createCalls(fetchImpl: ReturnType<typeof vi.fn<typeof fetch>>) {
  return fetchImpl.mock.calls.filter(([url, init]) => isCreateWorkflow(url, init as RequestInit));
}

function approveCalls(fetchImpl: ReturnType<typeof vi.fn<typeof fetch>>) {
  return fetchImpl.mock.calls.filter(([url]) => String(url).includes("/approve"));
}

function rejectCalls(fetchImpl: ReturnType<typeof vi.fn<typeof fetch>>) {
  return fetchImpl.mock.calls.filter(([url]) => String(url).includes("/reject"));
}

function executeCalls(fetchImpl: ReturnType<typeof vi.fn<typeof fetch>>) {
  return fetchImpl.mock.calls.filter(([url]) => String(url).includes("/execute"));
}

function renderWorkspace(options: {
  fetchImpl: ReturnType<typeof vi.fn<typeof fetch>>;
  permissions?: readonly EciPermission[];
}) {
  window.history.replaceState(null, "", mailboxWorkspacePath(GMAIL_ID));
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
        permissions: options.permissions ?? ALL_PERMISSIONS,
      })}
    >
      <App apiClient={apiClient} />
    </AuthStub>,
  );
}

async function selectAndAnalyze(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: /Ada Lovelace/ }));
  await user.click(screen.getByRole("button", { name: "Analyze message" }));
  expect(await screen.findByRole("heading", { name: "AI Analysis" })).toBeInTheDocument();
}

function mailboxFetch(
  options: {
    analysis?: unknown;
    create?: (body: string | undefined) => Response | Promise<Response>;
    approve?: () => Response | Promise<Response>;
    reject?: () => Response | Promise<Response>;
    execute?: () => Response | Promise<Response>;
    get?: () => Response | Promise<Response>;
    messages?: unknown;
    connectors?: unknown;
  } = {},
) {
  return vi.fn<typeof fetch>(async (input, init) => {
    const url = String(input);
    const requestInit = init as RequestInit | undefined;
    if (url.includes("/messages/analyze")) {
      return jsonResponse(200, options.analysis ?? analysisBody());
    }
    if (isCreateWorkflow(input, requestInit)) {
      const responder = options.create ?? (() => jsonResponse(201, workflowAction()));
      return responder(requestInit?.body as string | undefined);
    }
    if (url.includes("/approve")) {
      const responder =
        options.approve ??
        (() =>
          jsonResponse(
            200,
            workflowAction({
              status: "approved",
              approved_reply_body: SNAPSHOT_BODY,
              approved_at: "2026-08-25T16:05:00Z",
            }),
          ));
      return responder();
    }
    if (url.includes("/reject")) {
      const responder =
        options.reject ??
        (() =>
          jsonResponse(200, workflowAction({ status: "rejected", rejected_at: "2026-08-25T16:06:00Z" })));
      return responder();
    }
    if (url.includes("/execute")) {
      const responder =
        options.execute ??
        (() =>
          jsonResponse(
            200,
            workflowAction({
              status: "executed",
              approved_reply_body: SNAPSHOT_BODY,
              executed_at: "2026-08-25T16:07:00Z",
            }),
          ));
      return responder();
    }
    if (isGetWorkflow(input, requestInit)) {
      const responder = options.get ?? (() => jsonResponse(200, workflowAction()));
      return responder();
    }
    if (url.includes("/messages")) {
      return jsonResponse(
        200,
        options.messages ?? { items: [messageItem()], next_cursor: null },
      );
    }
    return jsonResponse(200, options.connectors ?? listBody([account()]));
  });
}

afterEach(() => {
  window.history.replaceState(null, "", "/");
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("workflow proposal", () => {
  it("does not propose when analysis_id is missing", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch({
      analysis: analysisBody({ analysis_id: undefined }),
    });
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    expect(screen.getByText("This analysis cannot be proposed for sending.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Propose reply" })).not.toBeInTheDocument();
    expect(createCalls(fetchImpl)).toHaveLength(0);
  });

  it("does not auto-create a WorkflowAction after analysis success", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch();
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    expect(screen.getByRole("button", { name: "Propose reply" })).toBeEnabled();
    expect(createCalls(fetchImpl)).toHaveLength(0);
    expect(executeCalls(fetchImpl)).toHaveLength(0);
  });

  it("does not propose without communications:workflow", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch();
    renderWorkspace({
      fetchImpl,
      permissions: ["communications:read", "communications:analyze"],
    });
    await selectAndAnalyze(user);
    expect(screen.getByRole("button", { name: "Propose reply" })).toBeDisabled();
    expect(screen.getByText(/communications:workflow permission/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Propose reply" }));
    expect(createCalls(fetchImpl)).toHaveLength(0);
  });

  it("sends exactly one create request with the current analysis_id", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch();
    const logs = ["info", "log", "debug", "warn", "error"] as const;
    const spies = logs.map((method) => vi.spyOn(console, method).mockImplementation(() => undefined));
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    await user.click(screen.getByRole("button", { name: "Propose reply" }));
    expect(await screen.findByText("Pending review")).toBeInTheDocument();
    expect(createCalls(fetchImpl)).toHaveLength(1);
    expect(createCalls(fetchImpl)[0]?.[1]).toEqual(
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ analysis_id: ANALYSIS_ID }),
      }),
    );
    expect(screen.queryByRole("button", { name: "Propose reply" })).not.toBeInTheDocument();
    expect(createCalls(fetchImpl)).toHaveLength(1);
    const serialized = spies.map((spy) => JSON.stringify(spy.mock.calls)).join("");
    expect(serialized).not.toContain(ANALYSIS_ID);
    expect(serialized).not.toContain(ACTION_ID);
    expect(serialized).not.toContain(SNAPSHOT_BODY);
    spies.forEach((spy) => spy.mockRestore());
  });

  it("does not automatically retry a failed proposal", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch({
      create: () => jsonResponse(503, { detail: "persistence timeout" }),
    });
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    await user.click(screen.getByRole("button", { name: "Propose reply" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("temporarily unavailable");
    await new Promise((resolve) => setTimeout(resolve, 40));
    expect(createCalls(fetchImpl)).toHaveLength(1);
    expect(screen.queryByText("persistence timeout")).not.toBeInTheDocument();
  });
});

describe("pending approve and reject", () => {
  it("renders pending review with Approve and Reject and without Send", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch();
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    await user.click(screen.getByRole("button", { name: "Propose reply" }));
    expect(await screen.findByText("Pending review")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Proposed reply" })).toBeInTheDocument();
    expect(screen.getByText(SNAPSHOT_BODY)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve reply" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Reject reply" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Send approved reply" })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain(ACTION_ID);
    expect(document.body.textContent).not.toContain(ANALYSIS_ID);
  });

  it("approves with one mutation and does not send", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch();
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    await user.click(screen.getByRole("button", { name: "Propose reply" }));
    await user.click(await screen.findByRole("button", { name: "Approve reply" }));
    expect(await screen.findByText("Approved")).toBeInTheDocument();
    expect(approveCalls(fetchImpl)).toHaveLength(1);
    expect(executeCalls(fetchImpl)).toHaveLength(0);
    expect(screen.queryByRole("button", { name: "Approve reply" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject reply" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send approved reply" })).toBeEnabled();
  });

  it("rejects with one mutation and does not send or recreate an action", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch();
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    await user.click(screen.getByRole("button", { name: "Propose reply" }));
    await user.click(await screen.findByRole("button", { name: "Reject reply" }));
    expect(await screen.findByText("Rejected")).toBeInTheDocument();
    expect(rejectCalls(fetchImpl)).toHaveLength(1);
    expect(executeCalls(fetchImpl)).toHaveLength(0);
    expect(createCalls(fetchImpl)).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Send approved reply" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve reply" })).not.toBeInTheDocument();
    expect(screen.getByText(/cannot be sent/)).toBeInTheDocument();
  });
});

describe("send confirmation", () => {
  async function reachApproved(user: ReturnType<typeof userEvent.setup>) {
    await selectAndAnalyze(user);
    await user.click(screen.getByRole("button", { name: "Propose reply" }));
    await user.click(await screen.findByRole("button", { name: "Approve reply" }));
    expect(await screen.findByRole("button", { name: "Send approved reply" })).toBeEnabled();
  }

  it("opens confirmation without executing, and cancel sends nothing", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch();
    renderWorkspace({ fetchImpl });
    await reachApproved(user);
    await user.click(screen.getByRole("button", { name: "Send approved reply" }));
    const dialog = screen.getByRole("dialog", { name: "Send approved reply?" });
    expect(dialog).toHaveTextContent("connected mailbox");
    expect(executeCalls(fetchImpl)).toHaveLength(0);
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(executeCalls(fetchImpl)).toHaveLength(0);
  });

  it("confirms exactly one execute request and disables duplicate submits", async () => {
    const user = userEvent.setup();
    let release: ((value: Response) => void) | undefined;
    const fetchImpl = mailboxFetch({
      execute: () =>
        new Promise<Response>((resolve) => {
          release = resolve;
        }),
    });
    renderWorkspace({ fetchImpl });
    await reachApproved(user);
    await user.click(screen.getByRole("button", { name: "Send approved reply" }));
    const dialog = screen.getByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: "Send approved reply" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    expect(await screen.findByText("Sending the approved reply")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send approved reply" })).not.toBeInTheDocument();
    expect(executeCalls(fetchImpl)).toHaveLength(1);
    release?.(
      jsonResponse(
        200,
        workflowAction({
          status: "executed",
          approved_reply_body: SNAPSHOT_BODY,
          executed_at: "2026-08-25T16:07:00Z",
        }),
      ),
    );
    expect(await screen.findByText("Reply sent")).toBeInTheDocument();
    expect(executeCalls(fetchImpl)).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Send approved reply" })).not.toBeInTheDocument();
  });

  it("does not execute automatically after approval", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch();
    renderWorkspace({ fetchImpl });
    await reachApproved(user);
    await new Promise((resolve) => setTimeout(resolve, 40));
    expect(executeCalls(fetchImpl)).toHaveLength(0);
  });
});

describe("workflow permissions", () => {
  it("allows analyze without workflow proposal", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch();
    renderWorkspace({
      fetchImpl,
      permissions: ["communications:read", "communications:analyze"],
    });
    await selectAndAnalyze(user);
    expect(screen.getByRole("button", { name: "Re-analyze message" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Propose reply" })).toBeDisabled();
    expect(createCalls(fetchImpl)).toHaveLength(0);
  });

  it("allows propose and approve without Send when send permission is missing", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch();
    renderWorkspace({
      fetchImpl,
      permissions: ["communications:read", "communications:analyze", "communications:workflow"],
    });
    await selectAndAnalyze(user);
    await user.click(screen.getByRole("button", { name: "Propose reply" }));
    await user.click(await screen.findByRole("button", { name: "Approve reply" }));
    expect(await screen.findByText("Approved")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send approved reply" })).not.toBeInTheDocument();
    expect(screen.getByText(/communications:send permission/)).toBeInTheDocument();
    expect(executeCalls(fetchImpl)).toHaveLength(0);
  });

  it("handles a stale frontend send claim when the API returns 403", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch({
      execute: () => jsonResponse(403, { detail: "missing send scope" }),
    });
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    await user.click(screen.getByRole("button", { name: "Propose reply" }));
    await user.click(await screen.findByRole("button", { name: "Approve reply" }));
    await user.click(await screen.findByRole("button", { name: "Send approved reply" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Send approved reply" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("communications:send permission");
    expect(screen.queryByText("missing send scope")).not.toBeInTheDocument();
    expect(executeCalls(fetchImpl)).toHaveLength(1);
  });
});

describe("workflow state machine", () => {
  it.each([
    ["pending", { status: "pending" as WorkflowActionStatus }, ["Approve reply", "Reject reply"], ["Send approved reply"]],
    [
      "approved",
      { status: "approved" as WorkflowActionStatus, approved_reply_body: SNAPSHOT_BODY },
      ["Send approved reply"],
      ["Approve reply", "Reject reply"],
    ],
    [
      "rejected",
      { status: "rejected" as WorkflowActionStatus, rejected_at: "2026-08-25T16:06:00Z" },
      [],
      ["Approve reply", "Reject reply", "Send approved reply"],
    ],
    [
      "executing",
      {
        status: "executing" as WorkflowActionStatus,
        approved_reply_body: SNAPSHOT_BODY,
      },
      ["Refresh status"],
      ["Approve reply", "Reject reply", "Send approved reply"],
    ],
    [
      "executed",
      {
        status: "executed" as WorkflowActionStatus,
        approved_reply_body: SNAPSHOT_BODY,
        executed_at: "2026-08-25T16:07:00Z",
      },
      [],
      ["Approve reply", "Reject reply", "Send approved reply"],
    ],
    [
      "failed",
      {
        status: "failed" as WorkflowActionStatus,
        approved_reply_body: SNAPSHOT_BODY,
        failed_at: "2026-08-25T16:08:00Z",
      },
      [],
      ["Approve reply", "Reject reply", "Send approved reply"],
    ],
  ])("renders %s controls from backend status", async (_status, overrides, present, absent) => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch({
      create: () => jsonResponse(201, workflowAction(overrides)),
    });
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    await user.click(screen.getByRole("button", { name: "Propose reply" }));
    expect(await screen.findByText(SNAPSHOT_BODY)).toBeInTheDocument();
    for (const name of present) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
    for (const name of absent) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
  });
});

describe("executing uncertainty", () => {
  it("treats HTTP 503 execute plus EXECUTING refresh as uncertain and does not retry send", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch({
      execute: () => jsonResponse(503, { detail: "provider timeout smtp stack" }),
      get: () =>
        jsonResponse(
          200,
          workflowAction({
            status: "executing",
            approved_reply_body: SNAPSHOT_BODY,
          }),
        ),
    });
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    await user.click(screen.getByRole("button", { name: "Propose reply" }));
    await user.click(await screen.findByRole("button", { name: "Approve reply" }));
    await user.click(await screen.findByRole("button", { name: "Send approved reply" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Send approved reply" }));
    expect(await screen.findByText("Sending status is uncertain.")).toBeInTheDocument();
    expect(screen.getByText(/may have reached the provider/)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Refresh status" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send approved reply" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retry send|try send again/i })).not.toBeInTheDocument();
    expect(screen.queryByText("provider timeout smtp stack")).not.toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 40));
    expect(executeCalls(fetchImpl)).toHaveLength(1);
  });
});

describe("executed and failed", () => {
  it("shows terminal sent state without a second execute", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch();
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    await user.click(screen.getByRole("button", { name: "Propose reply" }));
    await user.click(await screen.findByRole("button", { name: "Approve reply" }));
    await user.click(await screen.findByRole("button", { name: "Send approved reply" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Send approved reply" }));
    expect(await screen.findByText("Reply sent")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send approved reply" })).not.toBeInTheDocument();
    expect(screen.queryByText(/smtp|foundry|bedrock/i)).not.toBeInTheDocument();
    expect(executeCalls(fetchImpl)).toHaveLength(1);
  });

  it("treats FAILED as terminal without retry or revert", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch({
      execute: () =>
        jsonResponse(
          200,
          workflowAction({
            status: "failed",
            approved_reply_body: SNAPSHOT_BODY,
            failed_at: "2026-08-25T16:08:00Z",
          }),
        ),
    });
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    await user.click(screen.getByRole("button", { name: "Propose reply" }));
    await user.click(await screen.findByRole("button", { name: "Approve reply" }));
    await user.click(await screen.findByRole("button", { name: "Send approved reply" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Send approved reply" }));
    expect(await screen.findByText(/cannot be sent again/)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: "Send approved reply" })).not.toBeInTheDocument();
    expect(screen.queryByText("Approved")).not.toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 40));
    expect(executeCalls(fetchImpl)).toHaveLength(1);
    expect(createCalls(fetchImpl)).toHaveLength(1);
  });
});

describe("selection and re-analysis boundaries", () => {
  it("clears workflow when another message is selected", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch({
      messages: {
        items: [
          messageItem(),
          messageItem({
            provider_message_id: MESSAGE_ID_TWO,
            sender: "Grace Hopper",
            subject: "Compiler notes",
          }),
        ],
        next_cursor: null,
      },
    });
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    await user.click(screen.getByRole("button", { name: "Propose reply" }));
    expect(await screen.findByText(SNAPSHOT_BODY)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Grace Hopper/ }));
    expect(screen.queryByText(SNAPSHOT_BODY)).not.toBeInTheDocument();
    expect(screen.queryByText("Pending review")).not.toBeInTheDocument();
    expect(createCalls(fetchImpl)).toHaveLength(1);
  });

  it("does not mutate an existing workflow snapshot after re-analysis", async () => {
    const user = userEvent.setup();
    let analyzeCount = 0;
    const fetchImpl = mailboxFetch({
      analysis: undefined,
    });
    fetchImpl.mockImplementation(async (input, init) => {
      const url = String(input);
      const requestInit = init as RequestInit | undefined;
      if (url.includes("/messages/analyze")) {
        analyzeCount += 1;
        if (analyzeCount === 1) {
          return jsonResponse(200, analysisBody());
        }
        return jsonResponse(
          200,
          analysisBody({
            analysis: {
              summary: { text: "Compiler notes require a follow-up." },
              priority: { level: "medium" },
              category: "inquiry",
              action_items: [],
              draft_reply: { body: NEW_DRAFT_BODY },
            },
            analysis_id: ANALYSIS_ID_TWO,
          }),
        );
      }
      if (isCreateWorkflow(input, requestInit)) {
        const body = JSON.parse(String(requestInit?.body ?? "{}")) as { analysis_id?: string };
        if (body.analysis_id === ANALYSIS_ID_TWO) {
          return jsonResponse(
            201,
            workflowAction({
              analysis_id: ANALYSIS_ID_TWO,
              proposed_reply_body: NEW_DRAFT_BODY,
            }),
          );
        }
        return jsonResponse(201, workflowAction());
      }
      if (url.includes("/messages")) {
        return jsonResponse(200, { items: [messageItem()], next_cursor: null });
      }
      return jsonResponse(200, listBody([account()]));
    });
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    await user.click(screen.getByRole("button", { name: "Propose reply" }));
    expect(await screen.findByText(SNAPSHOT_BODY)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Re-analyze message" }));
    expect(await screen.findByText(NEW_DRAFT_BODY)).toBeInTheDocument();
    expect(screen.queryByText(SNAPSHOT_BODY)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Propose reply" })).toBeEnabled();
    expect(createCalls(fetchImpl)).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Propose reply" }));
    expect(await screen.findByRole("heading", { name: "Proposed reply" })).toBeInTheDocument();
    expect(screen.getAllByText(NEW_DRAFT_BODY).length).toBeGreaterThanOrEqual(2);
    expect(createCalls(fetchImpl)).toHaveLength(2);
    const second = JSON.parse(String(createCalls(fetchImpl)[1]?.[1]?.body ?? "{}")) as {
      analysis_id?: string;
    };
    expect(second.analysis_id).toBe(ANALYSIS_ID_TWO);
  });

  it("clears workflow on mailbox refresh", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch();
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    await user.click(screen.getByRole("button", { name: "Propose reply" }));
    expect(await screen.findByText(SNAPSHOT_BODY)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => {
      expect(screen.queryByText(SNAPSHOT_BODY)).not.toBeInTheDocument();
    });
    expect(createCalls(fetchImpl)).toHaveLength(1);
  });
});

describe("workflow privacy", () => {
  it("keeps workflow content in memory and does not log or persist it", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch();
    const logs = ["info", "log", "debug", "warn", "error"] as const;
    const spies = logs.map((method) => vi.spyOn(console, method).mockImplementation(() => undefined));
    renderWorkspace({ fetchImpl });
    await selectAndAnalyze(user);
    await user.click(screen.getByRole("button", { name: "Propose reply" }));
    expect(await screen.findByText(SNAPSHOT_BODY)).toBeInTheDocument();
    expect(window.localStorage.length).toBe(0);
    expect(window.location.href).not.toContain(SNAPSHOT_BODY);
    expect(window.location.href).not.toContain(ACTION_ID);
    expect(window.location.href).not.toContain(ANALYSIS_ID);
    expect(window.location.pathname).toBe(mailboxWorkspacePath(GMAIL_ID));
    expect(document.body.textContent).not.toContain(ACTION_ID);
    expect(document.body.textContent).not.toContain(ANALYSIS_ID);
    const serialized = spies.map((spy) => JSON.stringify(spy.mock.calls)).join("");
    expect(serialized).not.toContain(SNAPSHOT_BODY);
    expect(serialized).not.toContain(ACTION_ID);
    expect(serialized).not.toContain(ANALYSIS_ID);
    spies.forEach((spy) => spy.mockRestore());
  });
});
