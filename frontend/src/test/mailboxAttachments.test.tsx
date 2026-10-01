import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useAnalyzeAttachment } from "../hooks/useAnalyzeAttachment";
import { act, render, renderHook, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { tabularResult } from "./tabularFixtures";

import { App } from "../App";
import { EciApiClient } from "../api/client";
import type { ConnectorAccount } from "../api/connectorAccounts";
import type { AttachmentAnalysisResponse, AttachmentMetadataItem } from "../api/attachments";
import type { EciPermission } from "../auth/permissions";
import { mailboxWorkspacePath } from "../navigation/paths";
import { AuthStub, TEST_CONFIG, TEST_TOKEN, createAuthSession } from "./fixtures";
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
      <App apiClient={apiClient} config={TEST_CONFIG} />
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
    await user.click(await screen.findByRole("button", { name: /Ada Lovelace/ }, { timeout: 5000 }));
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

const XLSX_METADATA = attachmentItem({
  filename: "Budget.xlsx",
  media_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
});

function xlsxAnalysis(overrides: Partial<AttachmentAnalysisResponse> = {}) {
  return analysisResult({
    filename: XLSX_METADATA.filename,
    media_type: XLSX_METADATA.media_type,
    kind: "xlsx",
    action_items: [],
    tabular_result: tabularResult(),
    ...overrides,
  });
}

describe("Phase 21E XLSX mailbox experience", () => {
  it("offers only PDF/DOCX/TXT/XLSX Analyze and never analyzes while listing", async () => {
    const user = userEvent.setup();
    const items = ["xlsx", "pdf", "docx", "txt", "xls", "xlsm", "xlsb", "csv", "tsv"].map((extension) =>
      attachmentItem({ provider_attachment_id: extension, filename: `Data.${extension}`, media_type: "text/plain" }),
    );
    const fetchImpl = mailboxFetch(items);
    renderWorkspace({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: /Ada Lovelace/ }));
    await screen.findByText("Data.xlsx");
    expect(screen.getByText(/Excel workbook \(.xlsx\)/)).toBeInTheDocument();
    for (const extension of ["xlsx", "pdf", "docx", "txt"]) {
      expect(screen.getByRole("button", { name: `Analyze attachment: Data.${extension}` })).toBeEnabled();
    }
    for (const extension of ["xls", "xlsm", "xlsb", "csv", "tsv"]) {
      expect(screen.queryByRole("button", { name: `Analyze attachment: Data.${extension}` })).toBeNull();
    }
    expect(screen.getAllByText("Unsupported for analysis")).toHaveLength(5);
    expect(attachmentAnalyzeCalls(fetchImpl)).toHaveLength(0);
    expect(fetchImpl.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
  });

  it("uses the existing endpoint only on keyboard Analyze, blocks parallel clicks, and shows success", async () => {
    const user = userEvent.setup();
    let release: ((response: Response) => void) | undefined;
    const fetchImpl = mailboxFetch([XLSX_METADATA, attachmentItem({ provider_attachment_id: ATT_SIBLING })], {
      analyze: () => new Promise<Response>((resolve) => { release = resolve; }),
    });
    renderWorkspace({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: /Ada Lovelace/ }));
    const button = await screen.findByRole("button", { name: "Analyze attachment: Budget.xlsx" });
    expect(attachmentAnalyzeCalls(fetchImpl)).toHaveLength(0);
    button.focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("status")).toHaveTextContent("Analyzing attachment");
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    const sibling = screen.getByRole("button", { name: "Analyze attachment: Contract.pdf" });
    expect(sibling).toBeDisabled();
    await user.click(sibling);
    await user.dblClick(button);
    expect(attachmentAnalyzeCalls(fetchImpl)).toHaveLength(1);
    expect(attachmentAnalyzeCalls(fetchImpl)[0]).toEqual([
      `http://localhost:8000/api/v1/connector-accounts/${GMAIL_ID}/messages/attachments/analyze`,
      expect.objectContaining({ method: "POST", body: JSON.stringify({ provider_message_id: MESSAGE_ID_ONE, provider_attachment_id: ATT_PDF }) }),
    ]);
    release?.(jsonResponse(200, xlsxAnalysis()));
    expect(await screen.findByText(tabularResult().summary)).toBeInTheDocument();
    expect(screen.queryByText("Analyzing attachment")).toBeNull();
    expect(button).toBeEnabled();
    expect(sibling).toBeEnabled();
    expect(fetchImpl.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
    expect(mailboxAnalyzeCalls(fetchImpl)).toHaveLength(0);
  });

  it.each([
    [422, "attachment_unsupported", "This file type is not supported for analysis."],
    [422, "attachment_content_invalid", "Document extraction failed for this attachment."],
    [422, "attachment_security_blocked", "A security check blocked processing of this attachment."],
    [422, "attachment_exceeds_limit", "This file is too large to analyze."],
    [422, "attachment_parse_failed", "This document could not be read."],
    [503, "attachment_scanner_unavailable", "The attachment security scanner is unavailable."],
    [503, "provider_failure", "Attachment analysis is temporarily unavailable."],
    [500, "malformed_ai_output", "The attachment could not be analyzed."],
    [403, "forbidden", "Analyzing attachments requires the communications:analyze permission."],
    [404, "not_found", "This attachment is no longer available. Refresh the mailbox to update the list."],
    [500, "unexpected", "The attachment could not be analyzed."],
  ] as const)("normalizes XLSX error %s / %s without raw details or automatic retries", async (status, code, message) => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch([XLSX_METADATA], {
      analyze: () => jsonResponse(status, { code, detail: "SECRET workbook XML / provider response / stack trace" }),
    });
    renderWorkspace({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: /Ada Lovelace/ }));
    await user.click(await screen.findByRole("button", { name: "Analyze attachment: Budget.xlsx" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByRole("alert")).toHaveFocus();
    expect(screen.queryByText(/SECRET/)).toBeNull();
    expect(attachmentAnalyzeCalls(fetchImpl)).toHaveLength(1);
  });

  it("retries only on explicit request and clears the error after success", async () => {
    const user = userEvent.setup();
    let attempt = 0;
    const fetchImpl = mailboxFetch([XLSX_METADATA], {
      analyze: () => ++attempt === 1 ? jsonResponse(503, { code: "attachment_scanner_unavailable", detail: "Attachment scanner is unavailable." }) : jsonResponse(200, xlsxAnalysis()),
    });
    renderWorkspace({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: /Ada Lovelace/ }));
    await user.click(await screen.findByRole("button", { name: "Analyze attachment: Budget.xlsx" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The attachment security scanner is unavailable.");
    expect(attempt).toBe(1);
    await user.click(within(screen.getByRole("alert")).getByRole("button", { name: "Try again" }));
    expect(await screen.findByText(tabularResult().summary)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(attempt).toBe(2);
  });

  it("renders current and previous XLSX history without Analyze or retrieval", async () => {
    const user = userEvent.setup();
    const fetchImpl = mailboxFetch([XLSX_METADATA, attachmentItem({ provider_attachment_id: ATT_SIBLING })], {
      history: [
        xlsxAnalysis(),
        xlsxAnalysis({ attachment_analysis_id: PREVIOUS_ANALYSIS_ID, tabular_result: tabularResult({ summary: "Earlier workbook observations", source_truncated: true }) }),
        analysisResult({ attachment_analysis_id: "legacy", provider_attachment_id: ATT_SIBLING, tabular_result: null }),
      ],
    });
    renderWorkspace({ fetchImpl });
    await user.click(await screen.findByRole("button", { name: /Ada Lovelace/ }));
    expect(await screen.findByText(tabularResult().summary)).toBeInTheDocument();
    await user.click(screen.getByText("Previous analyses"));
    expect(screen.getByText("Earlier workbook observations")).toBeVisible();
    expect(screen.getByText("Analysis used a bounded sample of this workbook.")).toBeVisible();
    expect(screen.getByText(SUMMARY_TEXT)).toBeInTheDocument();
    expect(attachmentAnalyzeCalls(fetchImpl)).toHaveLength(0);
    expect(fetchImpl.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
  });
});

describe("attachment request concurrency", () => {
  function setupHook() {
    const apiClient = new EciApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: { acquireAccessToken: async () => TEST_TOKEN },
      fetchImpl: vi.fn<typeof fetch>(),
    });
    const queryClient = new QueryClient();
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    return { apiClient, wrapper };
  }

  it("guards same-tick duplicate and parallel requests before React renders pending state", async () => {
    const { apiClient, wrapper } = setupHook();
    let release: ((value: AttachmentAnalysisResponse) => void) | undefined;
    const analyze = vi.spyOn(apiClient, "analyzeMailboxAttachment").mockImplementation(() =>
      new Promise((resolve) => { release = resolve; }),
    );
    const { result } = renderHook(() => useAnalyzeAttachment(apiClient, GMAIL_ID, MESSAGE_ID_ONE), { wrapper });
    let first: Promise<void>;
    act(() => {
      first = result.current.analyze(ATT_PDF);
      void result.current.analyze(ATT_PDF);
      void result.current.analyze(ATT_SIBLING);
    });
    expect(analyze).toHaveBeenCalledTimes(1);
    await act(async () => { release?.(xlsxAnalysis()); await first; });
    expect(result.current.pendingId).toBeNull();
    expect(result.current.resultFor(ATT_PDF)?.kind).toBe("xlsx");
  });

  it("does not show an old message's pending result after navigation", async () => {
    const { apiClient, wrapper } = setupHook();
    const releases: ((value: AttachmentAnalysisResponse) => void)[] = [];
    vi.spyOn(apiClient, "analyzeMailboxAttachment").mockImplementation(() =>
      new Promise((resolve) => { releases.push(resolve); }),
    );
    const { result, rerender } = renderHook(({ message }) => useAnalyzeAttachment(apiClient, GMAIL_ID, message), {
      wrapper, initialProps: { message: MESSAGE_ID_ONE },
    });
    let first: Promise<void>;
    let second: Promise<void>;
    act(() => { first = result.current.analyze(ATT_PDF); });
    rerender({ message: MESSAGE_ID_TWO });
    act(() => { second = result.current.analyze(ATT_PDF); });
    await act(async () => { releases[0](xlsxAnalysis()); await first; });
    expect(result.current.resultFor(ATT_PDF)).toBeNull();
    expect(result.current.pendingId).toBe(ATT_PDF);
    await act(async () => { releases[1](xlsxAnalysis({ provider_message_id: MESSAGE_ID_TWO })); await second; });
    expect(result.current.resultFor(ATT_PDF)?.provider_message_id).toBe(MESSAGE_ID_TWO);
    expect(result.current.pendingId).toBeNull();
  });
});
