import { EciApiError } from "../api/errors";
import {
  REFRESH_LABEL,
  REFRESH_MAILBOX_LABEL,
  REFRESH_STATUS_LABEL,
  SESSION_UNUSABLE_COPY,
  TRY_AGAIN_LABEL,
} from "./copy";

export type ProductOperation =
  | "connector_list"
  | "connector_lifecycle"
  | "mailbox_list"
  | "analyze"
  | "attachment_list"
  | "attachment_analyze"
  | "attachment_history"
  | "propose"
  | "review"
  | "execute"
  | "workflow_refresh"
  | "api_smoke";

export type ProductErrorPresentation = {
  message: string;
  retryLabel: string | null;
  showSignIn: boolean;
  showDashboardLink: boolean;
};

const AUTHORIZATION_URL_INVALID = "authorization_url_invalid";

function statusOf(error: unknown): number | null {
  return error instanceof EciApiError ? error.status : null;
}

function presentation(options: {
  message: string;
  retryLabel?: string | null;
  showSignIn?: boolean;
  showDashboardLink?: boolean;
}): ProductErrorPresentation {
  return {
    message: options.message,
    retryLabel: options.retryLabel ?? null,
    showSignIn: options.showSignIn ?? false,
    showDashboardLink: options.showDashboardLink ?? false,
  };
}

function sessionExpired(): ProductErrorPresentation {
  return presentation({
    message: SESSION_UNUSABLE_COPY,
    showSignIn: true,
  });
}

export function presentProductError(
  operation: ProductOperation,
  error: unknown,
): ProductErrorPresentation {
  if (operation === "connector_lifecycle") {
    return presentConnectorLifecycleError(error);
  }
  const status = statusOf(error);
  if (status === 401) {
    return sessionExpired();
  }
  switch (operation) {
    case "connector_list":
      return presentConnectorListError(status);
    case "mailbox_list":
      return presentMailboxListError(status);
    case "analyze":
      return presentAnalyzeError(status);
    case "attachment_list":
      return presentAttachmentListError(status);
    case "attachment_analyze":
      return presentAttachmentAnalyzeError(error, status);
    case "attachment_history":
      return presentAttachmentHistoryError(status);
    case "propose":
      return presentProposeError(status);
    case "review":
      return presentReviewError(status);
    case "execute":
      return presentExecuteError(status);
    case "workflow_refresh":
      return presentWorkflowRefreshError(status);
    case "api_smoke":
      return presentApiSmokeError(status);
  }
}

function presentConnectorLifecycleError(error: unknown): ProductErrorPresentation {
  if (error instanceof Error && error.message === AUTHORIZATION_URL_INVALID) {
    return presentation({
      message: "Mailbox authorization could not be started safely.",
    });
  }
  const status = statusOf(error);
  if (status === 401) {
    return sessionExpired();
  }
  if (status === 403) {
    return presentation({
      message: "Connecting or disconnecting a mailbox requires the communications:connect permission.",
    });
  }
  if (status === 404) {
    return presentation({
      message: "That mailbox connection is unavailable.",
      showDashboardLink: true,
    });
  }
  if (status === 409) {
    return presentation({
      message: "This mailbox connection cannot be updated right now. Refresh and try again.",
      retryLabel: REFRESH_LABEL,
    });
  }
  if (status === 503) {
    return presentation({
      message: "Mailbox connection is temporarily unavailable.",
    });
  }
  return presentation({
    message: "Mailbox connection could not be completed.",
  });
}

function presentConnectorListError(status: number | null): ProductErrorPresentation {
  if (status === 403) {
    return presentation({
      message: "The signed-in account is missing a required permission.",
    });
  }
  if (status === 409) {
    return presentation({
      message: "Mailbox connections cannot be updated right now. Refresh and try again.",
      retryLabel: REFRESH_LABEL,
    });
  }
  if (status === 503) {
    return presentation({
      message: "Mailbox connections are temporarily unavailable.",
      retryLabel: TRY_AGAIN_LABEL,
    });
  }
  return presentation({
    message: "Mailbox connections could not be loaded.",
    retryLabel: status === 500 || status === null ? TRY_AGAIN_LABEL : null,
  });
}

function presentMailboxListError(status: number | null): ProductErrorPresentation {
  if (status === 400) {
    return presentation({
      message: "This mailbox page expired or is no longer valid.",
      retryLabel: REFRESH_MAILBOX_LABEL,
    });
  }
  if (status === 403) {
    return presentation({
      message: "Viewing this mailbox requires the communications:read permission.",
      showDashboardLink: true,
    });
  }
  if (status === 404) {
    return presentation({
      message: "That mailbox connection is unavailable.",
      showDashboardLink: true,
    });
  }
  if (status === 409) {
    return presentation({
      message: "This mailbox is not available right now.",
      showDashboardLink: true,
    });
  }
  if (status === 503) {
    return presentation({
      message: "Mailbox is temporarily unavailable.",
      retryLabel: TRY_AGAIN_LABEL,
    });
  }
  return presentation({
    message: "Mailbox messages could not be loaded.",
    retryLabel: status === 500 || status === null ? TRY_AGAIN_LABEL : null,
    showDashboardLink: true,
  });
}

function presentAnalyzeError(status: number | null): ProductErrorPresentation {
  if (status === 400) {
    return presentation({
      message: "The analysis request could not be completed.",
    });
  }
  if (status === 403) {
    return presentation({
      message: "The signed-in account is missing a required permission to analyze this message.",
    });
  }
  if (status === 404) {
    return presentation({
      message: "This message is no longer available. Refresh the mailbox to update the list.",
      retryLabel: REFRESH_MAILBOX_LABEL,
      showDashboardLink: true,
    });
  }
  if (status === 409) {
    return presentation({
      message: "This mailbox is not available right now.",
      showDashboardLink: true,
    });
  }
  if (status === 422) {
    return presentation({
      message: "The analysis request could not be validated.",
    });
  }
  if (status === 503) {
    return presentation({
      message: "Analysis could not be completed.",
      retryLabel: TRY_AGAIN_LABEL,
    });
  }
  return presentation({
    message: "The message could not be analyzed.",
    retryLabel: status === 500 || status === null ? TRY_AGAIN_LABEL : null,
  });
}

function presentAttachmentListError(status: number | null): ProductErrorPresentation {
  if (status === 403) {
    return presentation({
      message: "Viewing attachments requires the communications:read permission.",
      showDashboardLink: true,
    });
  }
  if (status === 404) {
    return presentation({
      message: "This message is no longer available. Refresh the mailbox to update the list.",
      retryLabel: REFRESH_MAILBOX_LABEL,
      showDashboardLink: true,
    });
  }
  if (status === 409) {
    return presentation({
      message: "This mailbox is not available right now.",
      showDashboardLink: true,
    });
  }
  if (status === 422) {
    return presentation({
      message: "Attachment details for this message are not supported.",
    });
  }
  if (status === 503) {
    return presentation({
      message: "Attachment details are temporarily unavailable.",
      retryLabel: TRY_AGAIN_LABEL,
    });
  }
  return presentation({
    message: "Attachment details could not be loaded.",
    retryLabel: status === 500 || status === null ? TRY_AGAIN_LABEL : null,
  });
}

function presentAttachmentAnalyzeError(
  error: unknown,
  status: number | null,
): ProductErrorPresentation {
  const detailClass = error instanceof EciApiError ? error.detailClass : null;
  if (detailClass === "unsupported") {
    return presentation({
      message: "This file type is not supported for analysis.",
    });
  }
  if (detailClass === "too_large" || status === 413) {
    return presentation({
      message: "This file is too large to analyze.",
    });
  }
  if (detailClass === "invalid_content") {
    return presentation({
      message: "Document extraction failed for this attachment.",
    });
  }
  if (detailClass === "processing_rejected") {
    return presentation({
      message: "A security check blocked processing of this attachment.",
    });
  }
  if (detailClass === "scanner_unavailable") {
    return presentation({
      message: "The attachment security scanner is unavailable.",
      retryLabel: TRY_AGAIN_LABEL,
    });
  }
  if (detailClass === "image_unavailable") {
    return presentation({
      message: "Image analysis is not available with the current AI provider.",
    });
  }
  if (status === 401) {
    return sessionExpired();
  }
  if (status === 403) {
    return presentation({
      message: "Analyzing attachments requires the communications:analyze permission.",
    });
  }
  if (status === 404) {
    return presentation({
      message: "This attachment is no longer available. Refresh the mailbox to update the list.",
      retryLabel: REFRESH_MAILBOX_LABEL,
      showDashboardLink: true,
    });
  }
  if (status === 409) {
    return presentation({
      message: "This mailbox is not available right now.",
      showDashboardLink: true,
    });
  }
  if (status === 422) {
    return presentation({
      message: "This attachment could not be analyzed.",
    });
  }
  if (status === 503) {
    return presentation({
      message: "Attachment analysis is temporarily unavailable.",
      retryLabel: TRY_AGAIN_LABEL,
    });
  }
  return presentation({
    message: "The attachment could not be analyzed.",
    retryLabel: status === 500 || status === null ? TRY_AGAIN_LABEL : null,
  });
}

function presentAttachmentHistoryError(status: number | null): ProductErrorPresentation {
  if (status === 403) {
    return presentation({
      message: "Viewing attachment analysis history requires the communications:analyze permission.",
    });
  }
  if (status === 503) {
    return presentation({
      message: "Attachment analysis history is temporarily unavailable.",
      retryLabel: TRY_AGAIN_LABEL,
    });
  }
  return presentation({
    message: "Previous attachment analyses could not be loaded.",
    retryLabel: status === 500 || status === null ? TRY_AGAIN_LABEL : null,
  });
}

function presentProposeError(status: number | null): ProductErrorPresentation {
  if (status === 403) {
    return presentation({
      message: "Proposing a reply requires the communications:workflow permission.",
    });
  }
  if (status === 404) {
    return presentation({
      message: "This analysis is no longer available to propose.",
    });
  }
  if (status === 409) {
    return presentation({
      message: "This analysis has no usable draft to propose.",
    });
  }
  if (status === 422) {
    return presentation({
      message: "The proposal request could not be validated.",
    });
  }
  if (status === 503) {
    return presentation({
      message: "Proposal is temporarily unavailable.",
      retryLabel: TRY_AGAIN_LABEL,
    });
  }
  return presentation({
    message: "The reply could not be proposed.",
    retryLabel: status === 500 || status === null ? TRY_AGAIN_LABEL : null,
  });
}

function presentReviewError(status: number | null): ProductErrorPresentation {
  if (status === 403) {
    return presentation({
      message: "Reviewing this reply requires the communications:workflow permission.",
    });
  }
  if (status === 404) {
    return presentation({
      message: "This workflow action is no longer available.",
    });
  }
  if (status === 409) {
    return presentation({
      message: "This workflow action changed. Refresh its status.",
      retryLabel: REFRESH_STATUS_LABEL,
    });
  }
  if (status === 503) {
    return presentation({
      message: "Workflow review is temporarily unavailable.",
      retryLabel: TRY_AGAIN_LABEL,
    });
  }
  return presentation({
    message: "The workflow action could not be updated.",
    retryLabel: status === 500 || status === null ? TRY_AGAIN_LABEL : null,
  });
}

function presentExecuteError(status: number | null): ProductErrorPresentation {
  if (status === 403) {
    return presentation({
      message: "Sending an approved reply requires the communications:send permission.",
    });
  }
  if (status === 404) {
    return presentation({
      message: "This workflow action is no longer available.",
    });
  }
  if (status === 409) {
    return presentation({
      message: "This reply cannot be sent right now. Refresh status or reconnect the mailbox.",
      retryLabel: REFRESH_STATUS_LABEL,
      showDashboardLink: true,
    });
  }
  if (status === 503) {
    return presentation({
      message: "Sending status is uncertain. Do not send again.",
      retryLabel: REFRESH_STATUS_LABEL,
    });
  }
  return presentation({
    message: "The approved reply could not be sent.",
    retryLabel: status === 500 ? REFRESH_STATUS_LABEL : null,
  });
}

function presentWorkflowRefreshError(status: number | null): ProductErrorPresentation {
  if (status === 403) {
    return presentation({
      message: "Refreshing workflow status requires the communications:workflow permission.",
    });
  }
  if (status === 404) {
    return presentation({
      message: "This workflow action is no longer available.",
    });
  }
  if (status === 503) {
    return presentation({
      message: "Workflow status could not be refreshed right now.",
      retryLabel: TRY_AGAIN_LABEL,
    });
  }
  return presentation({
    message: "Workflow status could not be refreshed.",
    retryLabel: status === 500 || status === null ? TRY_AGAIN_LABEL : null,
  });
}

function presentApiSmokeError(status: number | null): ProductErrorPresentation {
  if (status === 403) {
    return presentation({
      message: "The signed-in account is missing a required permission.",
    });
  }
  if (status === 503) {
    return presentation({
      message: "The API is temporarily unavailable.",
      retryLabel: TRY_AGAIN_LABEL,
    });
  }
  return presentation({
    message: "Protected API connectivity could not be verified.",
    retryLabel: status === 500 || status === null ? TRY_AGAIN_LABEL : null,
  });
}

export function workflowOperationFromError(
  errorOperation: "propose" | "approve" | "reject" | "execute" | "refresh" | null,
): ProductOperation | null {
  if (errorOperation === "propose") {
    return "propose";
  }
  if (errorOperation === "approve" || errorOperation === "reject") {
    return "review";
  }
  if (errorOperation === "execute") {
    return "execute";
  }
  if (errorOperation === "refresh") {
    return "workflow_refresh";
  }
  return null;
}
