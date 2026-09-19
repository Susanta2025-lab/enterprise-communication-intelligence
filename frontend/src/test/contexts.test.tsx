import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import { EciApiClient } from "../api/client";
import type { BusinessContext, ContextTimelineEntry } from "../api/contexts";
import type { EciPermission } from "../auth/permissions";
import { CONTEXTS_PATH, contextWorkspacePath } from "../navigation/paths";
import { AuthStub, TEST_CONFIG, TEST_TOKEN, createAuthSession } from "./fixtures";

const CONTEXT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const LINK_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const CONNECTOR_ID = "11111111-1111-4111-8111-111111111111";

function jsonResponse(status: number, body: unknown = {}): Response {
  if (status === 204) {
    return new Response(null, { status });
  }
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function context(overrides: Partial<BusinessContext> = {}): BusinessContext {
  return {
    id: CONTEXT_ID,
    type: "project",
    title: "Acme Project",
    description: "Notes",
    reference: "PRJ-1",
    status: "active",
    archived_at: null,
    created_at: "2026-09-01T10:00:00Z",
    updated_at: "2026-09-02T11:00:00Z",
    ...overrides,
  };
}

function timelineEntry(overrides: Partial<ContextTimelineEntry> = {}): ContextTimelineEntry {
  return {
    id: `context_created:${CONTEXT_ID}`,
    type: "context_created",
    occurred_at: "2026-09-01T10:00:00Z",
    title: "Context created",
    summary: null,
    source_type: "business_context",
    source_id: CONTEXT_ID,
    connector_account_id: null,
    provider_message_id: null,
    ...overrides,
  };
}

function renderContexts(options: {
  fetchImpl: ReturnType<typeof vi.fn<typeof fetch>>;
  permissions?: readonly EciPermission[];
  path?: string;
}) {
  window.history.replaceState(null, "", options.path ?? CONTEXTS_PATH);
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
        permissions: options.permissions ?? [
          "communications:read",
          "communications:analyze",
          "communications:connect",
        ],
      })}
    >
      <App apiClient={apiClient} config={TEST_CONFIG} />
    </AuthStub>,
  );
}

function defaultFetch(handler: (url: string, init?: RequestInit) => Response | null) {
  return vi.fn<typeof fetch>(async (input, init) => {
    const url = String(input);
    if (url.includes("/api/v1/me")) {
      return jsonResponse(200, { application_role: "user", is_owner: false });
    }
    const handled = handler(url, init);
    if (handled) {
      return handled;
    }
    if (url.includes("/connector-accounts")) {
      return jsonResponse(200, { items: [], limit: 20, offset: 0 });
    }
    return jsonResponse(500, { detail: `unhandled ${url}` });
  });
}

afterEach(() => {
  window.history.replaceState(null, "", "/");
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("contexts list", () => {
  it("loads contexts and opens a workspace", async () => {
    const user = userEvent.setup();
    const fetchImpl = defaultFetch((url) => {
      if (url.includes("/api/v1/contexts?") || url.endsWith("/api/v1/contexts")) {
        return jsonResponse(200, { items: [context()], limit: 50, offset: 0 });
      }
      if (url.includes(`/api/v1/contexts/${CONTEXT_ID}`) && !url.includes("/timeline")) {
        return jsonResponse(200, context());
      }
      return null;
    });
    renderContexts({ fetchImpl });

    expect(await screen.findByRole("heading", { name: "Contexts" })).toBeInTheDocument();
    expect(await screen.findByText("Acme Project")).toBeInTheDocument();
    expect(screen.getByTestId(`context-card-${CONTEXT_ID}`)).toHaveTextContent("Project");
    expect(screen.getByTestId(`context-card-${CONTEXT_ID}`)).toHaveTextContent("PRJ-1");
    expect(screen.getByTestId(`context-card-${CONTEXT_ID}`)).toHaveTextContent("Active");

    await user.click(screen.getByTestId(`context-card-${CONTEXT_ID}`));
    expect(await screen.findByRole("heading", { name: "Acme Project" })).toBeInTheDocument();
    expect(window.location.pathname).toBe(contextWorkspacePath(CONTEXT_ID));
  });

  it("shows empty state when there are no contexts", async () => {
    const fetchImpl = defaultFetch((url) => {
      if (url.includes("/api/v1/contexts")) {
        return jsonResponse(200, { items: [], limit: 50, offset: 0 });
      }
      return null;
    });
    renderContexts({ fetchImpl });
    expect(await screen.findByTestId("contexts-empty")).toBeInTheDocument();
    expect(screen.getByText("No contexts yet")).toBeInTheDocument();
  });

  it("filters by status using the list API", async () => {
    const user = userEvent.setup();
    const fetchImpl = defaultFetch((url) => {
      if (url.includes("/api/v1/contexts")) {
        return jsonResponse(200, { items: [], limit: 50, offset: 0 });
      }
      return null;
    });
    renderContexts({ fetchImpl });
    await screen.findByRole("heading", { name: "Contexts" });
    await user.selectOptions(screen.getByLabelText("Status"), "archived");
    await waitFor(() => {
      const listCalls = fetchImpl.mock.calls.filter(([url]) =>
        String(url).includes("/api/v1/contexts?"),
      );
      expect(
        listCalls.some(([url]) => String(url).includes("status=archived")),
      ).toBe(true);
    });
  });

  it("shows an API error on list failure", async () => {
    const fetchImpl = defaultFetch((url) => {
      if (url.includes("/api/v1/contexts")) {
        return jsonResponse(503, { detail: "unavailable" });
      }
      return null;
    });
    renderContexts({ fetchImpl });
    expect(await screen.findByText("Contexts are temporarily unavailable.")).toBeInTheDocument();
  });

  it("works without mailbox connection endpoints beyond identity", async () => {
    const fetchImpl = defaultFetch((url) => {
      if (url.includes("/api/v1/contexts")) {
        return jsonResponse(200, { items: [context()], limit: 50, offset: 0 });
      }
      return null;
    });
    renderContexts({ fetchImpl });
    expect(await screen.findByText("Acme Project")).toBeInTheDocument();
    expect(
      fetchImpl.mock.calls.every(([url]) => !String(url).includes("/messages")),
    ).toBe(true);
  });
});

describe("context create update archive restore", () => {
  it("creates a context from the list page", async () => {
    const user = userEvent.setup();
    const fetchImpl = defaultFetch((url, init) => {
      if (url.endsWith("/api/v1/contexts") && init?.method === "POST") {
        return jsonResponse(201, context({ title: "New Matter", type: "matter" }));
      }
      if (url.includes(`/api/v1/contexts/${CONTEXT_ID}`) && !url.includes("/timeline")) {
        return jsonResponse(200, context({ title: "New Matter", type: "matter" }));
      }
      if (url.includes("/api/v1/contexts")) {
        return jsonResponse(200, { items: [], limit: 50, offset: 0 });
      }
      return null;
    });
    renderContexts({ fetchImpl });
    await screen.findByRole("heading", { name: "Contexts" });
    await user.click(screen.getByRole("button", { name: "Create context" }));
    const createForm = screen.getByRole("heading", { name: "New context" }).parentElement!;
    await user.selectOptions(within(createForm).getByLabelText("Type"), "matter");
    await user.type(within(createForm).getByLabelText("Title"), "New Matter");
    await user.click(within(createForm).getByRole("button", { name: "Create" }));
    expect(await screen.findByRole("heading", { name: "New Matter" })).toBeInTheDocument();
  });

  it("validates empty title before calling the API", async () => {
    const user = userEvent.setup();
    const fetchImpl = defaultFetch((url) => {
      if (url.includes("/api/v1/contexts")) {
        return jsonResponse(200, { items: [], limit: 50, offset: 0 });
      }
      return null;
    });
    renderContexts({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: "Create context" }));
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Title is required.");
    expect(
      fetchImpl.mock.calls.filter(([, init]) => init?.method === "POST").length,
    ).toBe(0);
  });

  it("edits archive and restore on the workspace", async () => {
    const user = userEvent.setup();
    let current = context();
    const fetchImpl = defaultFetch((url, init) => {
      if (url.includes(`/api/v1/contexts/${CONTEXT_ID}/archive`) && init?.method === "POST") {
        current = {
          ...current,
          status: "archived",
          archived_at: "2026-09-03T12:00:00Z",
        };
        return jsonResponse(200, current);
      }
      if (url.includes(`/api/v1/contexts/${CONTEXT_ID}/restore`) && init?.method === "POST") {
        current = { ...current, status: "active", archived_at: null };
        return jsonResponse(200, current);
      }
      if (url.includes(`/api/v1/contexts/${CONTEXT_ID}`) && init?.method === "PATCH") {
        current = { ...current, title: "Renamed" };
        return jsonResponse(200, current);
      }
      if (
        url.includes(`/api/v1/contexts/${CONTEXT_ID}`) &&
        !url.includes("/communications") &&
        !url.includes("/timeline")
      ) {
        return jsonResponse(200, current);
      }
      if (url.includes("/api/v1/contexts?")) {
        return jsonResponse(200, { items: [current], limit: 50, offset: 0 });
      }
      return null;
    });
    renderContexts({ fetchImpl, path: contextWorkspacePath(CONTEXT_ID) });
    expect(await screen.findByRole("heading", { name: "Acme Project" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Edit" }));
    const title = screen.getByLabelText("Title");
    await user.clear(title);
    await user.type(title, "Renamed");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("heading", { name: "Renamed" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Archive" }));
    const archiveDialog = await screen.findByRole("dialog");
    await user.click(within(archiveDialog).getByRole("button", { name: "Archive" }));
    expect(await screen.findByRole("button", { name: "Restore" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Restore" }));
    const restoreDialog = await screen.findByRole("dialog");
    await user.click(within(restoreDialog).getByRole("button", { name: "Restore" }));
    expect(await screen.findByRole("button", { name: "Archive" })).toBeInTheDocument();
  });
});

describe("context association", () => {
  const ANALYSIS_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";

  function mailboxSuggestionFetch(
    handler: (url: string, init?: RequestInit) => Response | null,
  ) {
    return defaultFetch((url, init) => {
      if (url.includes("/messages/analyze") && !url.includes("/attachments")) {
        return jsonResponse(200, {
          analysis: {
            message_id: "msg-1",
            summary: { text: "Summary about Acme Project", confidence: 1 },
            priority: { level: "medium", rationale: null, confidence: 1 },
            category: "general",
            action_items: [],
            draft_reply: null,
          },
          provider: "mock",
          analysis_id: ANALYSIS_ID,
        });
      }
      if (url.includes("/messages") && !url.includes("/attachments")) {
        return jsonResponse(200, {
          items: [
            {
              provider_message_id: "msg-1",
              sender: "Ada",
              subject: "Hello",
              sent_at: "2026-09-01T10:00:00Z",
              received_at: "2026-09-01T10:01:00Z",
            },
          ],
          next_cursor: null,
        });
      }
      if (url.includes("/attachments")) {
        return jsonResponse(200, { items: [], truncated: false });
      }
      if (url.includes("/attachment-analyses")) {
        return jsonResponse(200, { items: [], limit: 20, offset: 0 });
      }
      if (url.includes("/connector-accounts")) {
        return jsonResponse(200, {
          items: [
            {
              id: CONNECTOR_ID,
              provider: "gmail",
              status: "active",
              granted_capabilities: ["mail.read"],
              created_at: "2026-09-01T00:00:00Z",
              updated_at: "2026-09-01T00:00:00Z",
            },
          ],
          limit: 20,
          offset: 0,
        });
      }
      if (url.includes("/api/v1/contexts?") && !url.includes("/communications")) {
        return jsonResponse(200, { items: [context()], limit: 50, offset: 0 });
      }
      return handler(url, init);
    });
  }

  it("associates a selected mailbox message with an active context", async () => {
    const user = userEvent.setup();
    const fetchImpl = defaultFetch((url, init) => {
      if (url.includes("/messages") && !url.includes("/attachments")) {
        return jsonResponse(200, {
          items: [
            {
              provider_message_id: "msg-1",
              sender: "Ada",
              subject: "Hello",
              sent_at: "2026-09-01T10:00:00Z",
              received_at: "2026-09-01T10:01:00Z",
            },
          ],
          next_cursor: null,
        });
      }
      if (url.includes("/attachments")) {
        return jsonResponse(200, { items: [], truncated: false });
      }
      if (url.includes("/attachment-analyses")) {
        return jsonResponse(200, { items: [], limit: 20, offset: 0 });
      }
      if (url.includes("/connector-accounts")) {
        return jsonResponse(200, {
          items: [
            {
              id: CONNECTOR_ID,
              provider: "gmail",
              status: "active",
              granted_capabilities: ["mail.read"],
              created_at: "2026-09-01T00:00:00Z",
              updated_at: "2026-09-01T00:00:00Z",
            },
          ],
          limit: 20,
          offset: 0,
        });
      }
      if (url.includes("/api/v1/contexts?") && !url.includes("/communications")) {
        return jsonResponse(200, { items: [context()], limit: 50, offset: 0 });
      }
      if (url.includes(`/api/v1/contexts/${CONTEXT_ID}/communications`) && init?.method === "POST") {
        return jsonResponse(201, {
          id: LINK_ID,
          business_context_id: CONTEXT_ID,
          connector_account_id: CONNECTOR_ID,
          provider_message_id: "msg-1",
          analysis_id: null,
          associated_at: "2026-09-03T10:00:00Z",
          association_source: "manual",
        });
      }
      return null;
    });
    renderContexts({
      fetchImpl,
      path: `/mailbox/${CONNECTOR_ID}`,
      permissions: ["communications:read", "communications:analyze", "communications:connect"],
    });
    await user.click(await screen.findByText("Hello"));
    await user.click(await screen.findByRole("button", { name: "Add to Context" }));
    await user.selectOptions(await screen.findByLabelText("Active context"), CONTEXT_ID);
    await user.click(screen.getByRole("button", { name: "Associate" }));
    expect(
      await screen.findByText("Communication associated with the selected context."),
    ).toBeInTheDocument();
  });

  it("loads AI suggestions and requires explicit associate", async () => {
    const user = userEvent.setup();
    let suggestionPosts = 0;
    let associatePosts = 0;
    const fetchImpl = mailboxSuggestionFetch((url, init) => {
      if (url.includes("/api/v1/contexts/suggestions") && init?.method === "POST") {
        suggestionPosts += 1;
        return jsonResponse(200, {
          suggestions: [
            {
              business_context_id: CONTEXT_ID,
              type: "project",
              title: "Acme Project",
              reference: "PRJ-1",
              match_strength: "high",
              rationale: "Title overlap",
            },
          ],
          no_match_reason: null,
        });
      }
      if (url.includes(`/api/v1/contexts/${CONTEXT_ID}/communications`) && init?.method === "POST") {
        associatePosts += 1;
        return jsonResponse(201, {
          id: LINK_ID,
          business_context_id: CONTEXT_ID,
          connector_account_id: CONNECTOR_ID,
          provider_message_id: "msg-1",
          analysis_id: ANALYSIS_ID,
          associated_at: "2026-09-03T10:00:00Z",
          association_source: "manual",
        });
      }
      return null;
    });
    renderContexts({
      fetchImpl,
      path: `/mailbox/${CONNECTOR_ID}`,
      permissions: ["communications:read", "communications:analyze", "communications:connect"],
    });
    await user.click(await screen.findByText("Hello"));
    await user.click(await screen.findByRole("button", { name: "Analyze message" }));
    await user.click(await screen.findByRole("button", { name: "Add to Context" }));
    expect(screen.getByTestId("context-manual-select")).toBeInTheDocument();
    expect(suggestionPosts).toBe(0);
    await user.click(await screen.findByRole("button", { name: "Suggest Context" }));
    expect(await screen.findByTestId("context-suggest-list")).toBeInTheDocument();
    expect(screen.getByText(/High match/i)).toBeInTheDocument();
    expect(suggestionPosts).toBe(1);
    expect(associatePosts).toBe(0);
    const suggested = screen.getByTestId("context-suggest-list");
    await user.click(within(suggested).getByRole("button", { name: "Associate" }));
    expect(
      await screen.findByText("Communication associated with the selected context."),
    ).toBeInTheDocument();
    expect(associatePosts).toBe(1);
  });

  it("shows no-match and AI failure while keeping manual association", async () => {
    const user = userEvent.setup();
    let mode: "empty" | "fail" = "empty";
    const fetchImpl = mailboxSuggestionFetch((url, init) => {
      if (url.includes("/api/v1/contexts/suggestions") && init?.method === "POST") {
        if (mode === "fail") {
          return jsonResponse(500, { detail: "AI failed" });
        }
        return jsonResponse(200, {
          suggestions: [],
          no_match_reason: "No suitable context found.",
        });
      }
      if (url.includes(`/api/v1/contexts/${CONTEXT_ID}/communications`) && init?.method === "POST") {
        return jsonResponse(201, {
          id: LINK_ID,
          business_context_id: CONTEXT_ID,
          connector_account_id: CONNECTOR_ID,
          provider_message_id: "msg-1",
          analysis_id: ANALYSIS_ID,
          associated_at: "2026-09-03T10:00:00Z",
          association_source: "manual",
        });
      }
      return null;
    });
    renderContexts({
      fetchImpl,
      path: `/mailbox/${CONNECTOR_ID}`,
      permissions: ["communications:read", "communications:analyze", "communications:connect"],
    });
    await user.click(await screen.findByText("Hello"));
    await user.click(await screen.findByRole("button", { name: "Analyze message" }));
    await user.click(await screen.findByRole("button", { name: "Add to Context" }));
    await user.click(await screen.findByRole("button", { name: "Suggest Context" }));
    expect(await screen.findByTestId("context-suggest-no-match")).toBeInTheDocument();
    mode = "fail";
    await user.click(screen.getByRole("button", { name: "Suggest Context" }));
    expect(await screen.findByTestId("context-suggest-error")).toBeInTheDocument();
    expect(screen.getByTestId("context-manual-select")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Active context"), CONTEXT_ID);
    await user.click(screen.getByRole("button", { name: "Associate" }));
    expect(
      await screen.findByText("Communication associated with the selected context."),
    ).toBeInTheDocument();
  });

  it("handles duplicate association conflicts gracefully", async () => {
    const user = userEvent.setup();
    const fetchImpl = defaultFetch((url, init) => {
      if (url.includes("/messages") && !url.includes("/attachments")) {
        return jsonResponse(200, {
          items: [
            {
              provider_message_id: "msg-1",
              sender: "Ada",
              subject: "Hello",
              sent_at: null,
              received_at: null,
            },
          ],
          next_cursor: null,
        });
      }
      if (url.includes("/attachments")) {
        return jsonResponse(200, { items: [], truncated: false });
      }
      if (url.includes("/attachment-analyses")) {
        return jsonResponse(200, { items: [], limit: 20, offset: 0 });
      }
      if (url.includes("/connector-accounts")) {
        return jsonResponse(200, {
          items: [
            {
              id: CONNECTOR_ID,
              provider: "gmail",
              status: "active",
              granted_capabilities: ["mail.read"],
              created_at: "2026-09-01T00:00:00Z",
              updated_at: "2026-09-01T00:00:00Z",
            },
          ],
          limit: 20,
          offset: 0,
        });
      }
      if (url.includes("/api/v1/contexts?")) {
        return jsonResponse(200, { items: [context()], limit: 50, offset: 0 });
      }
      if (url.includes("/communications") && init?.method === "POST") {
        return jsonResponse(409, { detail: "conflict" });
      }
      return null;
    });
    renderContexts({
      fetchImpl,
      path: `/mailbox/${CONNECTOR_ID}`,
      permissions: ["communications:read", "communications:analyze", "communications:connect"],
    });
    await user.click(await screen.findByText("Hello"));
    await user.click(await screen.findByRole("button", { name: "Add to Context" }));
    await user.selectOptions(await screen.findByLabelText("Active context"), CONTEXT_ID);
    await user.click(screen.getByRole("button", { name: "Associate" }));
    expect(
      await screen.findByText(
        /already associated with the context|context is archived/i,
      ),
    ).toBeInTheDocument();
  });

  it("removes an association from the workspace", async () => {
    const user = userEvent.setup();
    let links = [
      {
        id: LINK_ID,
        business_context_id: CONTEXT_ID,
        connector_account_id: CONNECTOR_ID,
        provider_message_id: "msg-1",
        analysis_id: null,
        associated_at: "2026-09-03T10:00:00Z",
        association_source: "manual",
      },
    ];
    const fetchImpl = defaultFetch((url, init) => {
      if (url.includes(`/api/v1/contexts/${CONTEXT_ID}/communications/${LINK_ID}`) && init?.method === "DELETE") {
        links = [];
        return jsonResponse(204);
      }
      if (url.includes(`/api/v1/contexts/${CONTEXT_ID}/communications`)) {
        return jsonResponse(200, { items: links, limit: 50, offset: 0 });
      }
      if (
        url.includes(`/api/v1/contexts/${CONTEXT_ID}`) &&
        !url.includes("/timeline")
      ) {
        return jsonResponse(200, context());
      }
      return null;
    });
    renderContexts({
      fetchImpl,
      path: contextWorkspacePath(CONTEXT_ID),
      permissions: ["communications:read", "communications:analyze"],
    });
    await screen.findByRole("heading", { name: "Acme Project" });
    await user.click(screen.getByRole("tab", { name: "Communications" }));
    expect(await screen.findByTestId(`context-link-${LINK_ID}`)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Remove from Context" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Remove from Context" }));
    expect(await screen.findByTestId("context-communications-empty")).toBeInTheDocument();
  });

  it("only offers active contexts for association", async () => {
    const user = userEvent.setup();
    const fetchImpl = defaultFetch((url) => {
      if (url.includes("/messages") && !url.includes("/attachments")) {
        return jsonResponse(200, {
          items: [
            {
              provider_message_id: "msg-1",
              sender: "Ada",
              subject: "Hello",
              sent_at: null,
              received_at: null,
            },
          ],
          next_cursor: null,
        });
      }
      if (url.includes("/attachments")) {
        return jsonResponse(200, { items: [], truncated: false });
      }
      if (url.includes("/attachment-analyses")) {
        return jsonResponse(200, { items: [], limit: 20, offset: 0 });
      }
      if (url.includes("/connector-accounts")) {
        return jsonResponse(200, {
          items: [
            {
              id: CONNECTOR_ID,
              provider: "gmail",
              status: "active",
              granted_capabilities: ["mail.read"],
              created_at: "2026-09-01T00:00:00Z",
              updated_at: "2026-09-01T00:00:00Z",
            },
          ],
          limit: 20,
          offset: 0,
        });
      }
      if (url.includes("/api/v1/contexts?")) {
        expect(url).toContain("status=active");
        return jsonResponse(200, { items: [context()], limit: 50, offset: 0 });
      }
      return null;
    });
    renderContexts({
      fetchImpl,
      path: `/mailbox/${CONNECTOR_ID}`,
      permissions: ["communications:read", "communications:analyze", "communications:connect"],
    });
    await user.click(await screen.findByText("Hello"));
    await user.click(await screen.findByRole("button", { name: "Add to Context" }));
    expect(await screen.findByLabelText("Active context")).toBeInTheDocument();
  });
});

describe("context timeline", () => {
  it("loads ordered timeline events", async () => {
    const user = userEvent.setup();
    const fetchImpl = defaultFetch((url) => {
      if (url.includes(`/api/v1/contexts/${CONTEXT_ID}/timeline`)) {
        return jsonResponse(200, {
          items: [
            timelineEntry({
              id: "association:1",
              type: "communication_associated",
              title: "Communication associated",
              occurred_at: "2026-09-03T12:00:00Z",
            }),
            timelineEntry(),
          ],
          limit: 50,
          offset: 0,
        });
      }
      if (url.includes(`/api/v1/contexts/${CONTEXT_ID}`)) {
        return jsonResponse(200, context());
      }
      return null;
    });
    renderContexts({ fetchImpl, path: contextWorkspacePath(CONTEXT_ID) });
    await screen.findByRole("heading", { name: "Acme Project" });
    await user.click(screen.getByRole("tab", { name: "Timeline" }));
    const entries = await screen.findAllByTestId(/timeline-entry-/);
    expect(entries[0]).toHaveTextContent("Communication associated");
    expect(entries[1]).toHaveTextContent("Context created");
  });

  it("shows empty and error timeline states", async () => {
    const user = userEvent.setup();
    const fetchImpl = defaultFetch((url) => {
      if (url.includes("/timeline")) {
        return jsonResponse(200, { items: [], limit: 50, offset: 0 });
      }
      if (url.includes(`/api/v1/contexts/${CONTEXT_ID}`)) {
        return jsonResponse(200, context());
      }
      return null;
    });
    renderContexts({ fetchImpl, path: contextWorkspacePath(CONTEXT_ID) });
    await user.click(await screen.findByRole("tab", { name: "Timeline" }));
    expect(await screen.findByTestId("context-timeline-empty")).toBeInTheDocument();
  });

  it("shows timeline load errors", async () => {
    const user = userEvent.setup();
    const fetchImpl = defaultFetch((url) => {
      if (url.includes("/timeline")) {
        return jsonResponse(503, { detail: "down" });
      }
      if (url.includes(`/api/v1/contexts/${CONTEXT_ID}`)) {
        return jsonResponse(200, context());
      }
      return null;
    });
    renderContexts({ fetchImpl, path: contextWorkspacePath(CONTEXT_ID) });
    await user.click(await screen.findByRole("tab", { name: "Timeline" }));
    expect(await screen.findByText("The timeline is temporarily unavailable.")).toBeInTheDocument();
  });
});

describe("contexts navigation", () => {
  it("exposes a Contexts nav entry", async () => {
    const fetchImpl = defaultFetch((url) => {
      if (url.includes("/api/v1/contexts")) {
        return jsonResponse(200, { items: [], limit: 50, offset: 0 });
      }
      return null;
    });
    renderContexts({ fetchImpl, path: "/" });
    expect(await screen.findByTestId("nav-contexts")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Contexts" })).toHaveAttribute("href", CONTEXTS_PATH);
  });
});
