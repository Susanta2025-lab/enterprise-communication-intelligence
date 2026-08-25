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
