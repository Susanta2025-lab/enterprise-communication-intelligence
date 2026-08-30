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
  | "bad_request"
  | "unavailable"
  | "http_error"
  | "interaction_required";

export class EciApiError extends Error {
  readonly name = "EciApiError";
  readonly status: number;
  readonly kind: ApiErrorKind;

  constructor(status: number, kind: ApiErrorKind, message: string) {
    super(message);
    this.status = status;
    this.kind = kind;
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
  if (status === 422) {
    return "validation";
  }
  if (status === 503) {
    return "unavailable";
  }
  return "http_error";
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
    case "interaction_required":
      return "Interactive authentication is required.";
    default:
      return "The operation could not be completed.";
  }
}
