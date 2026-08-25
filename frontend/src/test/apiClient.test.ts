import { describe, expect, it, vi } from "vitest";

import { EciApiClient } from "../api/client";
import {
  CONNECTOR_ACCOUNTS_PATH,
  EciApiError,
  GMAIL_AUTHORIZE_PATH,
  MICROSOFT_GRAPH_AUTHORIZE_PATH,
  PROTECTED_ANALYSES_SMOKE_PATH,
} from "../api/errors";
import {
  connectorAccountMessageAnalyzePath,
  connectorAccountMessagesPath,
  MAILBOX_UI_PAGE_SIZE,
} from "../api/mailbox";
import { InteractionRequiredError } from "../auth/tokenProvider";
import { TEST_TOKEN } from "./fixtures";

const REQUEST_ID = "11111111-1111-4111-8111-111111111111";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("ECI API client", () => {
  it("attaches a bearer token and request id for the analyses smoke contract", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => jsonResponse(200, { items: [], limit: 1, offset: 0 }));
    const client = new EciApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: { acquireAccessToken: async () => TEST_TOKEN },
      fetchImpl,
      createRequestId: () => REQUEST_ID,
    });
    const log = vi.spyOn(console, "info").mockImplementation(() => undefined);

    await expect(client.getAnalysesSmoke()).resolves.toEqual({
      items: [],
      limit: 1,
      offset: 0,
    });

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(fetchImpl).toHaveBeenCalledWith(
      expect.stringContaining(PROTECTED_ANALYSES_SMOKE_PATH),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: `Bearer ${TEST_TOKEN}`,
          "X-Request-ID": REQUEST_ID,
        }),
      }),
    );
    expect(JSON.stringify(log.mock.calls)).not.toContain(TEST_TOKEN);
  });

  it("lists owned connector accounts with a bearer token", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () =>
      jsonResponse(200, { items: [], limit: 20, offset: 0 }),
    );
    const client = new EciApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: { acquireAccessToken: async () => TEST_TOKEN },
      fetchImpl,
      createRequestId: () => REQUEST_ID,
    });
    await expect(client.listConnectorAccounts()).resolves.toEqual({
      items: [],
      limit: 20,
      offset: 0,
    });
    expect(fetchImpl).toHaveBeenCalledWith(
      expect.stringContaining(`${CONNECTOR_ACCOUNTS_PATH}?limit=20&offset=0`),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: `Bearer ${TEST_TOKEN}`,
          "X-Request-ID": REQUEST_ID,
        }),
      }),
    );
  });

  it("starts Gmail and Microsoft authorization without logging URLs", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes(GMAIL_AUTHORIZE_PATH)) {
        return jsonResponse(200, {
          authorization_url: "https://accounts.google.com/o/oauth2/v2/auth",
          expires_at: "2026-08-25T00:00:00Z",
        });
      }
      return jsonResponse(200, {
        authorization_url: "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize",
        expires_at: "2026-08-25T00:00:00Z",
      });
    });
    const log = vi.spyOn(console, "info").mockImplementation(() => undefined);
    const client = new EciApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: { acquireAccessToken: async () => TEST_TOKEN },
      fetchImpl,
    });
    await client.startGmailAuthorization();
    await client.startMicrosoftGraphAuthorization();
    expect(fetchImpl.mock.calls[0]?.[0]).toEqual(expect.stringContaining(GMAIL_AUTHORIZE_PATH));
    expect(fetchImpl.mock.calls[1]?.[0]).toEqual(
      expect.stringContaining(MICROSOFT_GRAPH_AUTHORIZE_PATH),
    );
    expect(JSON.stringify(log.mock.calls)).not.toContain("accounts.google.com");
    log.mockRestore();
  });

  it.each([
    [400, "bad_request"],
    [401, "unauthorized"],
    [403, "forbidden"],
    [404, "not_found"],
    [409, "conflict"],
    [422, "validation"],
    [503, "unavailable"],
  ] as const)("normalizes HTTP %s", async (status, kind) => {
    const fetchImpl = vi.fn<typeof fetch>(async () => jsonResponse(status, { detail: TEST_TOKEN }));
    const client = new EciApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: { acquireAccessToken: async () => TEST_TOKEN },
      fetchImpl,
    });

    try {
      await client.getAnalysesSmoke();
      throw new Error("expected EciApiError");
    } catch (error) {
      expect(error).toBeInstanceOf(EciApiError);
      const apiError = error as EciApiError;
      expect(apiError.status).toBe(status);
      expect(apiError.kind).toBe(kind);
      expect(apiError.message).not.toContain(TEST_TOKEN);
    }
  });

  it("does not call fetch when interactive authentication is required", async () => {
    const fetchImpl = vi.fn<typeof fetch>();
    const client = new EciApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: {
        acquireAccessToken: async () => {
          throw new InteractionRequiredError();
        },
      },
      fetchImpl,
    });

    await expect(client.getAnalysesSmoke()).rejects.toMatchObject({
      kind: "interaction_required",
    });
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});

const MAILBOX_ACCOUNT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const OPAQUE_CURSOR = "opaque/cursor+token=";
const PROVIDER_MESSAGE_ID = "provider-msg-secret-id";

describe("mailbox list API client", () => {
  function mailboxClient(fetchImpl: ReturnType<typeof vi.fn<typeof fetch>>) {
    return new EciApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: { acquireAccessToken: async () => TEST_TOKEN },
      fetchImpl,
      createRequestId: () => REQUEST_ID,
    });
  }

  it("requests the first page with the UI page size and no cursor", async () => {
    const body = {
      items: [
        {
          provider_message_id: PROVIDER_MESSAGE_ID,
          sender: "Ada Lovelace",
          subject: "Quarterly review",
          sent_at: "2026-08-25T15:30:00Z",
          received_at: "2026-08-25T15:31:00Z",
        },
      ],
      next_cursor: OPAQUE_CURSOR,
    };
    const fetchImpl = vi.fn<typeof fetch>(async () => jsonResponse(200, body));
    const client = mailboxClient(fetchImpl);
    const log = vi.spyOn(console, "info").mockImplementation(() => undefined);

    await expect(
      client.listMailboxMessages({ connectorAccountId: MAILBOX_ACCOUNT_ID }),
    ).resolves.toEqual(body);

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const requested = new URL(String(fetchImpl.mock.calls[0]?.[0]));
    expect(requested.pathname).toBe(connectorAccountMessagesPath(MAILBOX_ACCOUNT_ID));
    expect(requested.searchParams.get("page_size")).toBe(String(MAILBOX_UI_PAGE_SIZE));
    expect(requested.searchParams.has("cursor")).toBe(false);
    expect(fetchImpl.mock.calls[0]?.[1]).toEqual(
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: `Bearer ${TEST_TOKEN}`,
          "X-Request-ID": REQUEST_ID,
        }),
      }),
    );
    expect(JSON.stringify(log.mock.calls)).not.toContain(TEST_TOKEN);
    expect(JSON.stringify(log.mock.calls)).not.toContain(OPAQUE_CURSOR);
    expect(JSON.stringify(log.mock.calls)).not.toContain(PROVIDER_MESSAGE_ID);
    log.mockRestore();
  });

  it("sends an opaque cursor unchanged and does not decode it", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () =>
      jsonResponse(200, { items: [], next_cursor: null }),
    );
    const client = mailboxClient(fetchImpl);
    await client.listMailboxMessages({
      connectorAccountId: MAILBOX_ACCOUNT_ID,
      pageSize: MAILBOX_UI_PAGE_SIZE,
      cursor: OPAQUE_CURSOR,
    });
    const requested = new URL(String(fetchImpl.mock.calls[0]?.[0]));
    expect(requested.searchParams.get("cursor")).toBe(OPAQUE_CURSOR);
    expect(requested.searchParams.get("page_size")).toBe("10");
  });

  it.each([
    [400, "bad_request"],
    [401, "unauthorized"],
    [403, "forbidden"],
    [404, "not_found"],
    [409, "conflict"],
    [503, "unavailable"],
  ] as const)("normalizes mailbox HTTP %s", async (status, kind) => {
    const fetchImpl = vi.fn<typeof fetch>(async () =>
      jsonResponse(status, { detail: OPAQUE_CURSOR }),
    );
    const client = mailboxClient(fetchImpl);
    try {
      await client.listMailboxMessages({ connectorAccountId: MAILBOX_ACCOUNT_ID });
      throw new Error("expected EciApiError");
    } catch (error) {
      expect(error).toBeInstanceOf(EciApiError);
      const apiError = error as EciApiError;
      expect(apiError.status).toBe(status);
      expect(apiError.kind).toBe(kind);
      expect(apiError.message).not.toContain(OPAQUE_CURSOR);
      expect(apiError.message).not.toContain(PROVIDER_MESSAGE_ID);
    }
  });
});

describe("mailbox analyze API client", () => {
  function mailboxClient(fetchImpl: ReturnType<typeof vi.fn<typeof fetch>>) {
    return new EciApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: { acquireAccessToken: async () => TEST_TOKEN },
      fetchImpl,
      createRequestId: () => REQUEST_ID,
    });
  }

  const analysisBody = {
    analysis: {
      summary: { text: "The sender requested a quarterly review." },
      priority: { level: "high" },
      category: "request",
      action_items: [{ description: "Prepare the review packet" }],
      draft_reply: { body: "Thank you. I will follow up shortly." },
    },
    provider: "mock",
    analysis_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  };

  it("posts provider_message_id once with a lazy bearer token", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => jsonResponse(200, analysisBody));
    const client = mailboxClient(fetchImpl);
    const log = vi.spyOn(console, "info").mockImplementation(() => undefined);

    await expect(
      client.analyzeMailboxMessage({
        connectorAccountId: MAILBOX_ACCOUNT_ID,
        providerMessageId: PROVIDER_MESSAGE_ID,
      }),
    ).resolves.toEqual(analysisBody);

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const requested = new URL(String(fetchImpl.mock.calls[0]?.[0]));
    expect(requested.pathname).toBe(connectorAccountMessageAnalyzePath(MAILBOX_ACCOUNT_ID));
    expect(fetchImpl.mock.calls[0]?.[1]).toEqual(
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: `Bearer ${TEST_TOKEN}`,
          "X-Request-ID": REQUEST_ID,
          "Content-Type": "application/json",
        }),
        body: JSON.stringify({ provider_message_id: PROVIDER_MESSAGE_ID }),
      }),
    );
    expect(JSON.stringify(log.mock.calls)).not.toContain(TEST_TOKEN);
    expect(JSON.stringify(log.mock.calls)).not.toContain(PROVIDER_MESSAGE_ID);
    expect(JSON.stringify(log.mock.calls)).not.toContain(analysisBody.analysis.summary.text);
    expect(JSON.stringify(log.mock.calls)).not.toContain(analysisBody.analysis.draft_reply.body);
    expect(JSON.stringify(log.mock.calls)).not.toContain(analysisBody.analysis_id);
    log.mockRestore();
  });

  it.each([
    [400, "bad_request"],
    [401, "unauthorized"],
    [403, "forbidden"],
    [404, "not_found"],
    [409, "conflict"],
    [422, "validation"],
    [503, "unavailable"],
    [500, "http_error"],
  ] as const)("normalizes analyze HTTP %s", async (status, kind) => {
    const fetchImpl = vi.fn<typeof fetch>(async () =>
      jsonResponse(status, { detail: PROVIDER_MESSAGE_ID }),
    );
    const client = mailboxClient(fetchImpl);
    try {
      await client.analyzeMailboxMessage({
        connectorAccountId: MAILBOX_ACCOUNT_ID,
        providerMessageId: PROVIDER_MESSAGE_ID,
      });
      throw new Error("expected EciApiError");
    } catch (error) {
      expect(error).toBeInstanceOf(EciApiError);
      const apiError = error as EciApiError;
      expect(apiError.status).toBe(status);
      expect(apiError.kind).toBe(kind);
      expect(apiError.message).not.toContain(PROVIDER_MESSAGE_ID);
    }
  });
});

const WORKFLOW_ACTION_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
const WORKFLOW_ANALYSIS_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

describe("workflow action API client", () => {
  function workflowClient(fetchImpl: ReturnType<typeof vi.fn<typeof fetch>>) {
    return new EciApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: { acquireAccessToken: async () => TEST_TOKEN },
      fetchImpl,
      createRequestId: () => REQUEST_ID,
    });
  }

  const actionBody = {
    id: WORKFLOW_ACTION_ID,
    action_type: "reply",
    analysis_id: WORKFLOW_ANALYSIS_ID,
    status: "pending",
    proposed_reply_body: "Thank you. I will follow up shortly.",
    approved_reply_body: null,
    created_at: "2026-08-25T16:00:00Z",
    approved_at: null,
    rejected_at: null,
    executed_at: null,
    failed_at: null,
    has_execution_target: true,
  };

  it("creates a workflow action from analysis_id without logging sensitive fields", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => jsonResponse(201, actionBody));
    const log = vi.spyOn(console, "info").mockImplementation(() => undefined);
    const client = workflowClient(fetchImpl);

    await expect(client.createWorkflowAction({ analysisId: WORKFLOW_ANALYSIS_ID })).resolves.toEqual(
      actionBody,
    );

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const requested = new URL(String(fetchImpl.mock.calls[0]?.[0]));
    expect(requested.pathname).toBe("/api/v1/workflow-actions");
    expect(fetchImpl.mock.calls[0]?.[1]).toEqual(
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: `Bearer ${TEST_TOKEN}`,
          "X-Request-ID": REQUEST_ID,
          "Content-Type": "application/json",
        }),
        body: JSON.stringify({ analysis_id: WORKFLOW_ANALYSIS_ID }),
      }),
    );
    const serialized = JSON.stringify(log.mock.calls);
    expect(serialized).not.toContain(WORKFLOW_ANALYSIS_ID);
    expect(serialized).not.toContain(WORKFLOW_ACTION_ID);
    expect(serialized).not.toContain(actionBody.proposed_reply_body);
    log.mockRestore();
  });

  it("gets, approves, rejects, and executes using the owned action routes", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.endsWith("/approve")) {
        return jsonResponse(200, {
          ...actionBody,
          status: "approved",
          approved_reply_body: actionBody.proposed_reply_body,
        });
      }
      if (url.endsWith("/reject")) {
        return jsonResponse(200, { ...actionBody, status: "rejected" });
      }
      if (url.endsWith("/execute")) {
        return jsonResponse(200, { ...actionBody, status: "executed" });
      }
      return jsonResponse(200, actionBody);
    });
    const client = workflowClient(fetchImpl);

    await client.getWorkflowAction(WORKFLOW_ACTION_ID);
    await client.approveWorkflowAction(WORKFLOW_ACTION_ID);
    await client.rejectWorkflowAction(WORKFLOW_ACTION_ID);
    await client.executeWorkflowAction(WORKFLOW_ACTION_ID);

    expect(new URL(String(fetchImpl.mock.calls[0]?.[0])).pathname).toBe(
      `/api/v1/workflow-actions/${WORKFLOW_ACTION_ID}`,
    );
    expect(fetchImpl.mock.calls[0]?.[1]).toEqual(expect.objectContaining({ method: "GET" }));
    expect(new URL(String(fetchImpl.mock.calls[1]?.[0])).pathname).toBe(
      `/api/v1/workflow-actions/${WORKFLOW_ACTION_ID}/approve`,
    );
    expect(fetchImpl.mock.calls[1]?.[1]).toEqual(expect.objectContaining({ method: "POST" }));
    expect((fetchImpl.mock.calls[1]?.[1] as RequestInit).body).toBeUndefined();
    expect(new URL(String(fetchImpl.mock.calls[2]?.[0])).pathname).toBe(
      `/api/v1/workflow-actions/${WORKFLOW_ACTION_ID}/reject`,
    );
    expect(new URL(String(fetchImpl.mock.calls[3]?.[0])).pathname).toBe(
      `/api/v1/workflow-actions/${WORKFLOW_ACTION_ID}/execute`,
    );
    expect((fetchImpl.mock.calls[3]?.[1] as RequestInit).body).toBeUndefined();
  });

  it.each([
    [401, "unauthorized"],
    [403, "forbidden"],
    [404, "not_found"],
    [409, "conflict"],
    [422, "validation"],
    [503, "unavailable"],
    [500, "http_error"],
  ] as const)("normalizes workflow HTTP %s", async (status, kind) => {
    const fetchImpl = vi.fn<typeof fetch>(async () =>
      jsonResponse(status, { detail: WORKFLOW_ACTION_ID }),
    );
    const client = workflowClient(fetchImpl);
    try {
      await client.executeWorkflowAction(WORKFLOW_ACTION_ID);
      throw new Error("expected EciApiError");
    } catch (error) {
      expect(error).toBeInstanceOf(EciApiError);
      const apiError = error as EciApiError;
      expect(apiError.status).toBe(status);
      expect(apiError.kind).toBe(kind);
      expect(apiError.message).not.toContain(WORKFLOW_ACTION_ID);
    }
  });
});
