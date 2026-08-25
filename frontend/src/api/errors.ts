export const PROTECTED_ANALYSES_SMOKE_PATH = "/api/v1/analyses?limit=1";

export type AnalysisListResponse = {
  items: readonly unknown[];
  limit: number;
  offset: number;
};

export type ApiErrorKind =
  | "unauthorized"
  | "forbidden"
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
  if (status === 401) {
    return "unauthorized";
  }
  if (status === 403) {
    return "forbidden";
  }
  if (status === 503) {
    return "unavailable";
  }
  return "http_error";
}

export function messageForKind(kind: ApiErrorKind): string {
  switch (kind) {
    case "unauthorized":
      return "The API rejected the request. Sign in again.";
    case "forbidden":
      return "The signed-in account is missing a required permission.";
    case "unavailable":
      return "The API is temporarily unavailable.";
    case "interaction_required":
      return "Interactive authentication is required.";
    default:
      return "The API request failed.";
  }
}
