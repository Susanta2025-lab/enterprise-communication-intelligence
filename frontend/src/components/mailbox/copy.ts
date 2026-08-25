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
