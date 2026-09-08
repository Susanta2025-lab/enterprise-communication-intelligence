import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import { EciApiClient } from "../api/client";
import type { ConnectorAccount } from "../api/connectorAccounts";
import type { AttachmentAnalysisResponse, AttachmentMetadataItem } from "../api/attachments";
import type { EciPermission } from "../auth/permissions";
import { mailboxWorkspacePath } from "../navigation/paths";
import { AuthStub, TEST_TOKEN, createAuthSession } from "./fixtures";
import {
  attachmentAnalyzeCalls,
  attachmentMetadataCalls,
  jsonResponse,
  mailboxAnalyzeCalls,
} from "./mailboxFetch";

const GMAIL_ID = "11111111-1111-4111-8111-111111111111";
const MESSAGE_ID_ONE = "provider-msg-one-secret";
const MESSAGE_ID_TWO = "provider-msg-two-secret";
const ATT_PDF = "att-pdf-secret";
const ATT_ZIP = "att-zip-secret";
const ATT_SIBLING = "att-sibling-secret";
const ATT_INLINE = "att-inline-secret";
const ATT_LARGE = "att-large-secret";
const ATT_IMAGE = "att-image-secret";
const ATTACHMENT_ANALYSIS_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
const PREVIOUS_ANALYSIS_ID = "ffffffff-ffff-4fff-8fff-ffffffffffff";
const EXTRACTED_TEXT = "CONFIDENTIAL extracted contract body that must not render";
const SUMMARY_TEXT = "The contract is within the approved budget.";
const ACTION_TEXT = "Confirm the remaining signature.";

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
    sent_at: "2026-08-25T15:30:00Z",
    received_at: "2026-08-25T15:31:00Z",
    ...overrides,
  };
}

function attachmentItem(overrides: Partial<AttachmentMetadataItem> = {}): AttachmentMetadataItem {
  return {
    provider_attachment_id: ATT_PDF,
    filename: "Contract.pdf",
    media_type: "application/pdf",
    reported_size: 1_800_000,
    is_inline: false,
    disposition: "attachment",
    ...overrides,
  };
}

function analysisResult(overrides: Record<string, unknown> = {}): AttachmentAnalysisResponse {
  return {
    attachment_analysis_id: ATTACHMENT_ANALYSIS_ID,
    created_at: "2026-09-06T12:00:00Z",
    connector_account_id: GMAIL_ID,
    provider_message_id: MESSAGE_ID_ONE,
    provider_attachment_id: ATT_PDF,
    filename: "Contract.pdf",
    media_type: "application/pdf",
    kind: "pdf",
    extracted_content_status: "text",
    truncated: false,
    warnings: ["Dates may be approximate."],
    summary: { text: SUMMARY_TEXT },
    priority: { level: "high", rationale: "Signature still required." },
    category: "request",
    action_items: [{ description: ACTION_TEXT }],
    provider: "mock",
    ...overrides,
  };
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
        permissions: options.permissions ?? ["communications:read", "communications:analyze"],
      })}
    >
      <App apiClient={apiClient} />
    </AuthStub>,
  );
}

function mailboxFetch(
  attachments: readonly AttachmentMetadataItem[] = [],
  options: {
    analyze?: (body: { provider_attachment_id?: string }) => Response | Promise<Response>;
    history?: AttachmentAnalysisResponse[];
    emailAnalyze?: () => Response;
    aiImageInput?: "available" | "unavailable";
  } = {},
) {
  return vi.fn<typeof fetch>(async (input, init) => {
    const url = String(input);
    if (url.includes("/api/v1/health") || url.endsWith("/health")) {
      return jsonResponse(200, {
        status: "healthy",
        service: "Enterprise Communication Intelligence Platform",
        version: "0.1.0",
        environment: "development",
        attachment_scanner: "unavailable",
        ai_image_input: options.aiImageInput ?? "unavailable",
      });
    }
    if (url.includes("/attachments/analyze")) {
      const body = JSON.parse(String((init as RequestInit | undefined)?.body ?? "{}")) as {
        provider_attachment_id?: string;
      };
      if (options.analyze) {
        return options.analyze(body);
      }
      return jsonResponse(200, analysisResult({ provider_attachment_id: body.provider_attachment_id }));
    }
    if (url.includes("/attachment-analyses")) {
      return jsonResponse(200, { items: options.history ?? [], limit: 20, offset: 0 });
    }
    if (url.includes("/attachments")) {
      return jsonResponse(200, { items: attachments, truncated: false });
    }
    if (url.includes("/messages/analyze")) {
      return options.emailAnalyze
        ? options.emailAnalyze()
        : jsonResponse(200, {
            analysis: {
              summary: { text: "Email summary only." },
              priority: { level: "low" },
              category: "general",
              action_items: [],
              draft_reply: { body: "Thanks." },
            },
            provider: "mock",
            analysis_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
          });
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
}

afterEach(() => {
  window.history.replaceState(null, "", "/");
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("attachment metadata", () => {
  it("shows an empty attachments section when a message has none", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch([]);
    renderWorkspace({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: /Ada Lovelace/ }));
    expect(await screen.findByRole("heading", { name: "Attachments" })).toBeInTheDocument();
    expect(screen.getByTestId("attachments-empty")).toHaveTextContent("This message has no attachments.");
    expect(screen.queryByRole("button", { name: /Analyze attachment/ })).not.toBeInTheDocument();
    expect(attachmentAnalyzeCalls(fetchImpl)).toHaveLength(0);
  });

  it("renders one attachment and multiple attachments with inline, unsupported, and oversized states", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch([
      attachmentItem(),
      attachmentItem({
        provider_attachment_id: ATT_INLINE,
        filename: "banner.png",
        media_type: "image/png",
        reported_size: 20_480,
        is_inline: true,
        disposition: "inline",
      }),
      attachmentItem({
        provider_attachment_id: ATT_ZIP,
        filename: "payload.zip",
        media_type: "application/zip",
        reported_size: 4096,
      }),
      attachmentItem({
        provider_attachment_id: ATT_LARGE,
        filename: "huge.pdf",
        media_type: "application/pdf",
        reported_size: 5 * 1024 * 1024 + 1,
      }),
    ]);
    renderWorkspace({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: /Ada Lovelace/ }));
    expect(await screen.findByText("Contract.pdf")).toBeInTheDocument();
    expect(screen.getByText("banner.png")).toBeInTheDocument();
    expect(screen.getByText(/Inline/)).toBeInTheDocument();
    expect(screen.getByText("payload.zip")).toBeInTheDocument();
    expect(screen.getByText("Unsupported for analysis")).toBeInTheDocument();
    expect(screen.getByText("huge.pdf")).toBeInTheDocument();
    expect(screen.getByText("Too large to analyze")).toBeInTheDocument();
    expect(
      screen.getByText("Image analysis unavailable with current AI provider"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyze attachment: Contract.pdf" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Analyze attachment: banner.png" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Analyze attachment: payload.zip" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Analyze attachment: huge.pdf" })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain(ATT_PDF);
    expect(document.body.textContent).not.toContain(ATT_ZIP);
  });

  it("offers Analyze for JPEG/PNG only when platform health reports image input available", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch(
      [
        attachmentItem({
          provider_attachment_id: ATT_IMAGE,
          filename: "chart.png",
          media_type: "image/png",
          reported_size: 4096,
        }),
      ],
      { aiImageInput: "available" },
    );
    renderWorkspace({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: /Ada Lovelace/ }));
    expect(await screen.findByRole("button", { name: "Analyze attachment: chart.png" })).toBeEnabled();
    expect(
      screen.queryByText("Image analysis unavailable with current AI provider"),
    ).not.toBeInTheDocument();
  });
});

describe("explicit Analyze attachment", () => {
  it("does not call attachment analyze when a message is opened or metadata is shown", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch([attachmentItem(), attachmentItem({
      provider_attachment_id: ATT_SIBLING,
      filename: "Notes.txt",
      media_type: "text/plain",
      reported_size: 120,
    })]);
    renderWorkspace({ fetchImpl });
    expect(await screen.findByRole("button", { name: /Ada Lovelace/ })).toBeInTheDocument();
    expect(attachmentAnalyzeCalls(fetchImpl)).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: /Ada Lovelace/ }));
    expect(await screen.findByText("Contract.pdf")).toBeInTheDocument();
    expect(attachmentMetadataCalls(fetchImpl).length).toBeGreaterThan(0);
    expect(attachmentAnalyzeCalls(fetchImpl)).toHaveLength(0);
    expect(mailboxAnalyzeCalls(fetchImpl)).toHaveLength(0);
  });

  it("posts only the selected attachment id after an explicit click", async () => {
    const user = userEvent.setup();
    const seen: string[] = [];
    const fetchImpl = mailboxFetch(
      [
        attachmentItem(),
        attachmentItem({
          provider_attachment_id: ATT_SIBLING,
          filename: "Notes.txt",
          media_type: "text/plain",
          reported_size: 120,
        }),
      ],
      {
        analyze: (body) => {
          seen.push(body.provider_attachment_id ?? "");
          return jsonResponse(200, analysisResult({ provider_attachment_id: body.provider_attachment_id }));
        },
      },
    );
    renderWorkspace({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: /Ada Lovelace/ }));
    await user.click(await screen.findByRole("button", { name: "Analyze attachment: Contract.pdf" }));
    expect(await screen.findByText(SUMMARY_TEXT)).toBeInTheDocument();
    expect(seen).toEqual([ATT_PDF]);
    expect(attachmentAnalyzeCalls(fetchImpl)).toHaveLength(1);
    const requested = attachmentAnalyzeCalls(fetchImpl)[0];
    expect(requested?.[1]).toEqual(
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          provider_message_id: MESSAGE_ID_ONE,
          provider_attachment_id: ATT_PDF,
        }),
      }),
    );
    expect(screen.getByText("Notes.txt")).toBeInTheDocument();
    expect(screen.getAllByTestId("attachment-status").some((node) => node.textContent === "Not analyzed")).toBe(
      true,
    );
  });
});

describe("attachment state and error mapping", () => {
  it("shows a loading state and disables repeated clicks for the selected attachment", async () => {
    const user = userEvent.setup();
    let release: ((value: Response) => void) | undefined;
    const fetchImpl = mailboxFetch([attachmentItem()], {
      analyze: () =>
        new Promise<Response>((resolve) => {
          release = resolve;
        }),
    });
    renderWorkspace({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: /Ada Lovelace/ }));
    const button = await screen.findByRole("button", { name: "Analyze attachment: Contract.pdf" });
    await user.click(button);
    const analyzing = await screen.findAllByText("Analyzing attachment");
    expect(analyzing).toHaveLength(1);
    expect(screen.getByTestId("attachment-status")).toHaveTextContent("Analyzing attachment");
    expect(screen.queryByTestId("attachment-analyzing")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyze attachment: Contract.pdf" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Ada Lovelace/ })).toBeEnabled();
    release?.(jsonResponse(200, analysisResult()));
    expect(await screen.findByText(SUMMARY_TEXT)).toBeInTheDocument();
  });

  it.each([
    [422, "Attachment is not supported.", "This file type is not supported for analysis."],
    [422, "Attachment exceeds limits.", "This file is too large to analyze."],
    [
      422,
      "Attachment was blocked by security policy.",
      "A security check blocked processing of this attachment.",
    ],
    [422, "Attachment could not be processed.", "This document could not be read."],
    [422, "Attachment content is invalid.", "Document extraction failed for this attachment."],
    [503, "Attachment scanner is unavailable.", "The attachment security scanner is unavailable."],
    [409, "Image analysis is not available.", "Image analysis is not available with the current AI provider."],
    [500, "foundry stack trace", "The attachment could not be analyzed."],
  ] as const)("maps HTTP %s detail to controlled copy", async (status, detail, message) => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch(
      [
        attachmentItem({
          provider_attachment_id: ATT_IMAGE,
          filename: "scan.jpg",
          media_type: "image/jpeg",
          reported_size: 4096,
        }),
      ],
      {
        aiImageInput: "available",
        analyze: () => jsonResponse(status, { detail }),
      },
    );
    renderWorkspace({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: /Ada Lovelace/ }));
    await user.click(await screen.findByRole("button", { name: "Analyze attachment: scan.jpg" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.queryByText(detail)).not.toBeInTheDocument();
    expect(screen.queryByText("foundry stack trace")).not.toBeInTheDocument();
  });

  it("keeps backend image-unavailable enforcement when frontend gating is bypassed", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch(
      [
        attachmentItem({
          provider_attachment_id: ATT_IMAGE,
          filename: "scan.jpg",
          media_type: "image/jpeg",
          reported_size: 4096,
        }),
      ],
      {
        aiImageInput: "available",
        analyze: () =>
          jsonResponse(409, {
            detail: "Image analysis is not available.",
            code: "attachment_image_unavailable",
          }),
      },
    );
    renderWorkspace({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: /Ada Lovelace/ }));
    await user.click(await screen.findByRole("button", { name: "Analyze attachment: scan.jpg" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Image analysis is not available with the current AI provider.",
    );
    expect(attachmentAnalyzeCalls(fetchImpl)).toHaveLength(1);
  });

  it("maps a network failure without exposing internals", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch([attachmentItem()], {
      analyze: () => {
        throw new TypeError("Failed to fetch");
      },
    });
    renderWorkspace({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: /Ada Lovelace/ }));
    await user.click(await screen.findByRole("button", { name: "Analyze attachment: Contract.pdf" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The attachment could not be analyzed.");
    expect(screen.queryByText("Failed to fetch")).not.toBeInTheDocument();
  });
});

describe("attachment result presentation", () => {
  it("renders structured fields, truncation, warnings, and no extracted text or workflow controls", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch([attachmentItem()], {
      analyze: () =>
        jsonResponse(
          200,
          analysisResult({
            truncated: true,
            extracted_content_status: "truncated_text",
          }),
        ),
    });
    renderWorkspace({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: /Ada Lovelace/ }));
    await user.click(await screen.findByRole("button", { name: "Analyze attachment: Contract.pdf" }));
    expect(await screen.findByText(SUMMARY_TEXT)).toBeInTheDocument();
    expect(screen.getByText("High")).toBeInTheDocument();
    expect(screen.getByText("Request")).toBeInTheDocument();
    expect(screen.getByText(ACTION_TEXT)).toBeInTheDocument();
    expect(screen.getByTestId("attachment-truncation-indicator")).toHaveTextContent(
      "Analysis used a bounded portion of the document.",
    );
    expect(screen.getByText("Dates may be approximate.")).toBeInTheDocument();
    expect(screen.getByText("mock")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain(EXTRACTED_TEXT);
    expect(screen.queryByRole("button", { name: "Propose reply" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve reply" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send approved reply" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Execute$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Send approved/i })).not.toBeInTheDocument();
  });

  it("shows previous analyses for the selected attachment", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch([attachmentItem()], {
      history: [
        analysisResult({
          attachment_analysis_id: PREVIOUS_ANALYSIS_ID,
          summary: { text: "Earlier review of the same contract." },
          created_at: "2026-09-05T12:00:00Z",
        }),
      ],
    });
    renderWorkspace({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: /Ada Lovelace/ }));
    expect(await screen.findByText("Earlier review of the same contract.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Propose reply" })).not.toBeInTheDocument();
  });
});

describe("email and attachment analyze isolation", () => {
  it("keeps email Analyze independent from attachment Analyze", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch([attachmentItem()]);
    renderWorkspace({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: /Ada Lovelace/ }));
    await user.click(await screen.findByRole("button", { name: "Analyze message" }));
    expect(await screen.findByText("Email summary only.")).toBeInTheDocument();
    expect(attachmentAnalyzeCalls(fetchImpl)).toHaveLength(0);
    expect(mailboxAnalyzeCalls(fetchImpl)).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Analyze attachment: Contract.pdf" }));
    expect(await screen.findByText(SUMMARY_TEXT)).toBeInTheDocument();
    expect(attachmentAnalyzeCalls(fetchImpl)).toHaveLength(1);
    expect(mailboxAnalyzeCalls(fetchImpl)).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Propose reply" })).toBeInTheDocument();
    const attachmentRegion = screen.getByRole("heading", { name: "Attachment analysis" }).closest("article");
    expect(attachmentRegion).not.toBeNull();
    expect(within(attachmentRegion as HTMLElement).queryByRole("button", { name: "Propose reply" })).toBeNull();
  });
});
