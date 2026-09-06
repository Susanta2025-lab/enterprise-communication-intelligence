import { SESSION_UNUSABLE_COPY } from "../errors/copy";

export const PROTECTED_ANALYSES_SMOKE_PATH = "/api/v1/analyses?limit=1";
export const CONNECTOR_ACCOUNTS_PATH = "/api/v1/connector-accounts";
export const GMAIL_AUTHORIZE_PATH = "/api/v1/connector-accounts/gmail/authorize";
export const GMAIL_CONNECT_ANOTHER_AUTHORIZE_PATH =
  "/api/v1/connector-accounts/gmail/authorize/another";
export const MICROSOFT_GRAPH_AUTHORIZE_PATH =
  "/api/v1/connector-accounts/microsoft_graph/authorize";
export const MICROSOFT_GRAPH_CONNECT_ANOTHER_AUTHORIZE_PATH =
  "/api/v1/connector-accounts/microsoft_graph/authorize/another";

export type AnalysisListResponse = {
  items: readonly unknown[];
  limit: number;
  offset: number;
};

export type ApiErrorKind =
  | "unauthorized"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "validation"
  | "payload_too_large"
  | "bad_request"
  | "unavailable"
  | "http_error"
  | "interaction_required";

export type AttachmentDetailClass =
  | "unsupported"
  | "too_large"
  | "invalid_content"
  | "processing_rejected"
  | "scanner_unavailable"
  | "image_unavailable";

const KNOWN_ATTACHMENT_DETAILS: Record<string, AttachmentDetailClass> = {
  "Attachment is not supported.": "unsupported",
  "Attachment exceeds limits.": "too_large",
  "Attachment content is invalid.": "invalid_content",
  "Attachment could not be processed.": "processing_rejected",
  "Attachment scanner is unavailable.": "scanner_unavailable",
  "Image analysis is not available.": "image_unavailable",
};

export class EciApiError extends Error {
  readonly name = "EciApiError";
  readonly status: number;
  readonly kind: ApiErrorKind;
  readonly detailClass: AttachmentDetailClass | null;

  constructor(
    status: number,
    kind: ApiErrorKind,
    message: string,
    detailClass: AttachmentDetailClass | null = null,
  ) {
    super(message);
    this.status = status;
    this.kind = kind;
    this.detailClass = detailClass;
  }
}

export function kindForStatus(status: number): ApiErrorKind {
  if (status === 400) {
    return "bad_request";
  }
  if (status === 401) {
    return "unauthorized";
  }
  if (status === 403) {
    return "forbidden";
  }
  if (status === 404) {
    return "not_found";
  }
  if (status === 409) {
    return "conflict";
  }
  if (status === 413) {
    return "payload_too_large";
  }
  if (status === 422) {
    return "validation";
  }
  if (status === 503) {
    return "unavailable";
  }
  return "http_error";
}

export function classifyAttachmentDetail(detail: unknown): AttachmentDetailClass | null {
  if (typeof detail !== "string") {
    return null;
  }
  return KNOWN_ATTACHMENT_DETAILS[detail] ?? null;
}

export function messageForKind(kind: ApiErrorKind): string {
  switch (kind) {
    case "unauthorized":
      return SESSION_UNUSABLE_COPY;
    case "forbidden":
      return "The signed-in account is missing a required permission.";
    case "not_found":
      return "That mailbox connection is unavailable.";
    case "conflict":
      return "This mailbox connection cannot be updated right now. Refresh and try again.";
    case "validation":
      return "The request could not be validated.";
    case "bad_request":
      return "The request could not be completed.";
    case "unavailable":
      return "The API is temporarily unavailable.";
    case "payload_too_large":
      return "The request could not be validated.";
    case "interaction_required":
      return "Interactive authentication is required.";
    default:
      return "The operation could not be completed.";
  }
}
