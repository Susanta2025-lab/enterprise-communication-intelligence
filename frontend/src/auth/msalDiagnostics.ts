/**
 * Production-safe MSAL diagnostics for External ID / browser auth.
 *
 * Logs only boolean counts, interaction status enums, event type names, and
 * sanitized error identifiers (errorCode / AADSTS / short structured subError).
 * Never log tokens, auth codes, PKCE, full authorize URLs, emails, tenant/client
 * IDs, correlation IDs, account identifiers, message identifiers, or attachment
 * identifiers.
 */

export type MsalDiagDetails = {
  readonly eventType?: string;
  readonly interactionStatus?: string;
  readonly accountCount?: number;
  readonly hasActiveAccount?: boolean;
  readonly hasAuthParamsInHash?: boolean;
  readonly hasAuthParamsInQuery?: boolean;
  readonly errorName?: string;
  readonly errorCode?: string;
  readonly aadstsCode?: string;
  readonly subError?: string;
};

export type AuthLocationScan = {
  readonly hasAuthParamsInHash: boolean;
  readonly hasAuthParamsInQuery: boolean;
};

/** Max length for a structured OAuth subError before it is treated as unsafe text. */
const MAX_SAFE_SUB_ERROR_LENGTH = 64;

const AADSTS_CODE = /\bAADSTS\d+\b/i;

function stripLeading(value: string, marker: "#" | "?"): string {
  if (!value) {
    return "";
  }
  return value.startsWith(marker) ? value.slice(1) : value;
}

function isAuthResponseParams(params: URLSearchParams): boolean {
  if (!params.has("state")) {
    return false;
  }
  return (
    params.has("code") ||
    params.has("error") ||
    params.has("ear_jwe") ||
    params.has("client_info")
  );
}

/**
 * Reports whether the current URL appears to carry an OAuth redirect response.
 * Used for diagnostics only — does not log parameter values.
 */
export function scanAuthRedirectLocation(
  location: { hash: string; search: string } = typeof window !== "undefined"
    ? window.location
    : { hash: "", search: "" },
): AuthLocationScan {
  return {
    hasAuthParamsInHash: isAuthResponseParams(
      new URLSearchParams(stripLeading(location.hash, "#")),
    ),
    hasAuthParamsInQuery: isAuthResponseParams(
      new URLSearchParams(stripLeading(location.search, "?")),
    ),
  };
}

function readStringField(record: object, key: string): string | undefined {
  const value = (record as Record<string, unknown>)[key];
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function extractAadstsCode(errorMessage?: string, message?: string): string | undefined {
  for (const candidate of [errorMessage, message]) {
    if (!candidate) {
      continue;
    }
    const match = AADSTS_CODE.exec(candidate);
    if (match) {
      return match[0].toUpperCase();
    }
  }
  return undefined;
}

function extractSafeSubError(record: object): string | undefined {
  const subError = readStringField(record, "subError");
  if (!subError) {
    return undefined;
  }
  if (subError.length > MAX_SAFE_SUB_ERROR_LENGTH) {
    return undefined;
  }
  // Structured OAuth suberrors are short tokens, not free-form descriptions.
  if (!/^[A-Za-z0-9._-]+$/.test(subError)) {
    return undefined;
  }
  return subError;
}

export type SanitizedMsalError = {
  readonly errorName?: string;
  readonly errorCode?: string;
  readonly aadstsCode?: string;
  readonly subError?: string;
};

/**
 * Extracts only safe MSAL/Entra error identifiers for console diagnostics.
 * Never returns message bodies, URLs, correlation/trace IDs, or tokens.
 */
export function sanitizeMsalError(error: unknown): SanitizedMsalError {
  if (!error || typeof error !== "object") {
    return { errorName: typeof error };
  }

  const errorName = readStringField(error, "name");
  const errorCode =
    readStringField(error, "errorCode") ?? readStringField(error, "code");
  const aadstsCode = extractAadstsCode(
    readStringField(error, "errorMessage"),
    readStringField(error, "message"),
  );
  const subError = extractSafeSubError(error);

  return {
    ...(errorName ? { errorName } : {}),
    ...(errorCode ? { errorCode } : {}),
    ...(aadstsCode ? { aadstsCode } : {}),
    ...(subError ? { subError } : {}),
  };
}

export function logMsalDiag(message: string, details: MsalDiagDetails = {}): void {
  console.info(`[eci-msal] ${message}`, details);
}

export function logMsalDiagError(message: string, error: unknown, details: MsalDiagDetails = {}): void {
  logMsalDiag(message, { ...details, ...sanitizeMsalError(error) });
}
