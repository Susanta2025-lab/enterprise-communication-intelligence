import { EciApiError } from "../../api/errors";

export const NO_SUBJECT_LABEL = "(No subject)";

export function displaySubject(subject: string | null | undefined): string {
  if (!subject || !subject.trim()) {
    return NO_SUBJECT_LABEL;
  }
  return subject;
}

export function mailboxListErrorMessage(error: unknown): string {
  if (error instanceof EciApiError) {
    switch (error.status) {
      case 400:
        return "This mailbox page expired or is no longer valid.";
      case 401:
        return "The API rejected the request. Sign in again.";
      case 403:
        return "Viewing this mailbox requires the communications:read permission.";
      case 404:
        return "That mailbox connection is unavailable.";
      case 409:
        return "This mailbox is not available right now.";
      case 503:
        return "The mailbox provider is temporarily unavailable. Try again.";
      default:
        return "Mailbox messages could not be loaded.";
    }
  }
  return "Mailbox messages could not be loaded.";
}

export const ANALYZE_ACTION_LABEL = "Analyze message";
export const REANALYZE_ACTION_LABEL = "Re-analyze message";
export const ANALYZE_PERMISSION_HINT =
  "Analyzing messages requires the communications:analyze permission.";
export const NO_ACTION_ITEMS_COPY = "No action items identified.";
export const NO_DRAFT_COPY = "No draft suggestion was generated.";
export const SUMMARY_UNAVAILABLE_COPY = "Summary is unavailable.";
export const DRAFT_SUGGESTION_HEADING = "AI draft suggestion";
export const DRAFT_BOUNDARY_COPY = "AI-generated suggestion. Not approved or sent.";

const PRIORITY_LABELS: Record<string, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  critical: "Critical",
};

const CATEGORY_LABELS: Record<string, string> = {
  general: "General",
  request: "Request",
  incident: "Incident",
  approval: "Approval",
  notification: "Notification",
  inquiry: "Inquiry",
  other: "Other",
};

export function priorityLabel(level: string | null | undefined): string {
  if (!level) {
    return "Unavailable";
  }
  return PRIORITY_LABELS[level] ?? level;
}

export function categoryLabel(category: string | null | undefined): string {
  if (!category) {
    return "Unavailable";
  }
  return CATEGORY_LABELS[category] ?? category;
}

export function analyzeErrorMessage(error: unknown): string {
  if (error instanceof EciApiError) {
    switch (error.status) {
      case 400:
        return "The analysis request could not be completed.";
      case 401:
        return "The API rejected the request. Sign in again.";
      case 403:
        return "The signed-in account is missing a required permission to analyze this message.";
      case 404:
        return "This message is no longer available. Refresh the mailbox to update the list.";
      case 409:
        return "This mailbox is not available right now.";
      case 422:
        return "The analysis request could not be validated.";
      case 503:
        return "Analysis is temporarily unavailable. Try again.";
      default:
        return "The message could not be analyzed.";
    }
  }
  return "The message could not be analyzed.";
}

export const PROPOSE_REPLY_LABEL = "Propose reply";
export const APPROVE_REPLY_LABEL = "Approve reply";
export const REJECT_REPLY_LABEL = "Reject reply";
export const SEND_APPROVED_REPLY_LABEL = "Send approved reply";
export const REFRESH_WORKFLOW_STATUS_LABEL = "Refresh status";
export const WORKFLOW_REVIEW_HEADING = "Workflow review";
export const WORKFLOW_PROPOSAL_HEADING = "Workflow proposal";
export const PROPOSED_REPLY_HEADING = "Proposed reply";
export const APPROVED_REPLY_HEADING = "Approved reply";
export const WORKFLOW_SNAPSHOT_BOUNDARY =
  "Workflow snapshot. This text is not editable and is not sent until you approve and confirm send.";
export const APPROVED_SNAPSHOT_BOUNDARY =
  "Approved communication. This text is not editable. Sending requires a separate confirmation.";
export const WORKFLOW_PERMISSION_HINT =
  "Proposing and reviewing replies requires the communications:workflow permission.";
export const SEND_PERMISSION_HINT =
  "Sending an approved reply requires the communications:send permission.";
export const ANALYSIS_NOT_PROPOSABLE_COPY = "This analysis cannot be proposed for sending.";
export const ANALYSIS_NO_DRAFT_COPY = "This analysis has no draft suggestion to propose.";
export const EXECUTION_UNCERTAIN_TITLE = "Sending status is uncertain.";
export const EXECUTION_UNCERTAIN_COPY =
  "The request may have reached the provider. Do not send again.";
export const SEND_IN_PROGRESS_COPY = "Sending the approved reply";
export const EXECUTED_SUCCESS_COPY = "Reply sent";
export const FAILED_TERMINAL_COPY =
  "Send could not be completed. This action cannot be sent again.";
export const REJECTED_TERMINAL_COPY =
  "This reply was rejected. It cannot be sent. Re-analyze the message to propose a new reply.";
export const SEND_CONFIRM_TITLE = "Send approved reply?";
export const SEND_CONFIRM_DESCRIPTION =
  "This will send the approved reply through the connected mailbox. This action may not be reversible.";
export const SEND_NOT_EXECUTABLE_COPY =
  "This reply cannot be sent through the current mailbox connection.";
export const PENDING_REVIEW_LABEL = "Pending review";
export const APPROVED_STATUS_LABEL = "Approved";
export const REJECTED_STATUS_LABEL = "Rejected";
export const EXECUTING_STATUS_LABEL = "Sending status is uncertain";
export const EXECUTED_STATUS_LABEL = "Reply sent";
export const FAILED_STATUS_LABEL = "Send could not be completed";

export function workflowStatusLabel(status: string): string {
  switch (status) {
    case "pending":
      return PENDING_REVIEW_LABEL;
    case "approved":
      return APPROVED_STATUS_LABEL;
    case "rejected":
      return REJECTED_STATUS_LABEL;
    case "executing":
      return EXECUTING_STATUS_LABEL;
    case "executed":
      return EXECUTED_STATUS_LABEL;
    case "failed":
      return FAILED_STATUS_LABEL;
    default:
      return "Unknown status";
  }
}

export function proposeErrorMessage(error: unknown): string {
  if (error instanceof EciApiError) {
    switch (error.status) {
      case 401:
        return "The API rejected the request. Sign in again.";
      case 403:
        return "Proposing a reply requires the communications:workflow permission.";
      case 404:
        return "This analysis is no longer available to propose.";
      case 409:
        return "This analysis has no usable draft to propose.";
      case 422:
        return "The proposal request could not be validated.";
      case 503:
        return "Proposal is temporarily unavailable. Try again.";
      default:
        return "The reply could not be proposed.";
    }
  }
  return "The reply could not be proposed.";
}

export function reviewErrorMessage(error: unknown): string {
  if (error instanceof EciApiError) {
    switch (error.status) {
      case 401:
        return "The API rejected the request. Sign in again.";
      case 403:
        return "Reviewing this reply requires the communications:workflow permission.";
      case 404:
        return "This workflow action is no longer available.";
      case 409:
        return "This workflow action is no longer in the expected state. Refresh status.";
      case 503:
        return "Workflow review is temporarily unavailable.";
      default:
        return "The workflow action could not be updated.";
    }
  }
  return "The workflow action could not be updated.";
}

export function executeErrorMessage(error: unknown): string {
  if (error instanceof EciApiError) {
    switch (error.status) {
      case 401:
        return "The API rejected the request. Sign in again.";
      case 403:
        return "Sending an approved reply requires the communications:send permission.";
      case 404:
        return "This workflow action is no longer available.";
      case 409:
        return "This reply cannot be sent right now. Refresh status or reconnect the mailbox.";
      case 503:
        return "The send request could not be completed. Refresh status before taking another action.";
      default:
        return "The approved reply could not be sent.";
    }
  }
  return "The approved reply could not be sent.";
}

export function refreshWorkflowErrorMessage(error: unknown): string {
  if (error instanceof EciApiError) {
    switch (error.status) {
      case 401:
        return "The API rejected the request. Sign in again.";
      case 403:
        return "Refreshing workflow status requires the communications:workflow permission.";
      case 404:
        return "This workflow action is no longer available.";
      case 503:
        return "Workflow status could not be refreshed right now.";
      default:
        return "Workflow status could not be refreshed.";
    }
  }
  return "Workflow status could not be refreshed.";
}

export function proposeRetryLabel(error: unknown): string | null {
  if (!(error instanceof EciApiError)) {
    return "Retry";
  }
  if (error.status === 503 || error.status === 500 || error.kind === "http_error") {
    return "Retry";
  }
  return null;
}

export function reviewRetryLabel(error: unknown): string | null {
  if (!(error instanceof EciApiError)) {
    return null;
  }
  if (error.status === 409) {
    return REFRESH_WORKFLOW_STATUS_LABEL;
  }
  if (error.status === 503 || error.status === 500 || error.kind === "http_error") {
    return "Retry";
  }
  return null;
}

export function executeRetryLabel(error: unknown): string | null {
  if (!(error instanceof EciApiError)) {
    return null;
  }
  if (error.status === 409 || error.status === 503) {
    return REFRESH_WORKFLOW_STATUS_LABEL;
  }
  return null;
}

export function analyzeRetryLabel(error: unknown): string | null {
  if (!(error instanceof EciApiError)) {
    return "Retry";
  }
  if (error.status === 404) {
    return "Refresh mailbox";
  }
  if (error.status === 503 || error.status === 500 || error.kind === "http_error") {
    return "Retry";
  }
  return null;
}

export function mailboxRetryLabel(error: unknown): string | null {
  if (!(error instanceof EciApiError)) {
    return "Try again";
  }
  if (error.status === 400) {
    return "Refresh mailbox";
  }
  if (error.status === 503 || error.kind === "http_error") {
    return "Try again";
  }
  return null;
}
