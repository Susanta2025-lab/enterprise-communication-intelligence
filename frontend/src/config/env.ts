import { isEciPermission } from "../auth/permissions";

export type EnvRecord = Record<string, string | boolean | undefined>;

export type FrontendConfig = {
  readonly apiBaseUrl: string;
  readonly entraSpaClientId: string;
  readonly entraRedirectUri: string;
  readonly eciApiScopes: readonly string[];
  readonly entraAuthority: string;
  readonly knownAuthorities: readonly string[];
};

export class FrontendConfigError extends Error {
  readonly name = "FrontendConfigError";

  constructor(message: string) {
    super(message);
  }
}

const GUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const AUTHORITY_HOSTNAME =
  /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$/i;

function readString(env: EnvRecord, key: string): string {
  const raw = env[key];
  if (typeof raw !== "string") {
    throw new FrontendConfigError(`${key} is missing.`);
  }
  const value = raw.trim();
  if (!value) {
    throw new FrontendConfigError(`${key} is missing.`);
  }
  return value;
}

function parseHttpUrl(key: string, value: string): URL {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new FrontendConfigError(`${key} is not a valid URL.`);
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new FrontendConfigError(`${key} must be an http(s) URL.`);
  }
  if (parsed.username || parsed.password || parsed.hash) {
    throw new FrontendConfigError(`${key} is not a valid URL.`);
  }
  return parsed;
}

export function parseEciApiScopes(raw: string): readonly string[] {
  const parts = raw
    .split(/[,\s]+/)
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length === 0) {
    throw new FrontendConfigError("VITE_ECI_API_SCOPES is missing or empty.");
  }

  const seen = new Set<string>();
  for (const scope of parts) {
    if (scope.includes(".default")) {
      throw new FrontendConfigError(
        "VITE_ECI_API_SCOPES must use explicit delegated scopes, not .default.",
      );
    }
    let permission: string;
    try {
      const url = new URL(scope);
      if (url.protocol !== "api:") {
        throw new FrontendConfigError(
          "VITE_ECI_API_SCOPES must contain full ECI scope identifiers.",
        );
      }
      permission = url.pathname.replace(/^\/+/, "").split("/").at(-1) ?? "";
    } catch (error) {
      if (error instanceof FrontendConfigError) {
        throw error;
      }
      throw new FrontendConfigError(
        "VITE_ECI_API_SCOPES must contain full ECI scope identifiers.",
      );
    }
    if (!isEciPermission(permission)) {
      throw new FrontendConfigError(
        "VITE_ECI_API_SCOPES must use exact communications:* permission names.",
      );
    }
    if (seen.has(permission)) {
      throw new FrontendConfigError("VITE_ECI_API_SCOPES contains duplicate permissions.");
    }
    seen.add(permission);
  }

  return Object.freeze([...parts]);
}

export function parseEntraAuthority(raw: string): {
  readonly authority: string;
  readonly knownAuthorities: readonly string[];
} {
  const parsed = parseHttpUrl("VITE_ENTRA_AUTHORITY", raw);
  if (parsed.protocol !== "https:") {
    throw new FrontendConfigError("VITE_ENTRA_AUTHORITY must be an https URL.");
  }
  if (parsed.search) {
    throw new FrontendConfigError("VITE_ENTRA_AUTHORITY is not a valid URL.");
  }
  if (!AUTHORITY_HOSTNAME.test(parsed.hostname) || !/[a-z]/i.test(parsed.hostname)) {
    throw new FrontendConfigError("VITE_ENTRA_AUTHORITY hostname is invalid.");
  }

  const pathSegments = parsed.pathname.split("/").filter(Boolean);
  if (pathSegments.length === 0) {
    throw new FrontendConfigError("VITE_ENTRA_AUTHORITY must include a tenant path.");
  }
  if (pathSegments.some((segment) => segment === "." || segment === "..")) {
    throw new FrontendConfigError("VITE_ENTRA_AUTHORITY is not a valid URL.");
  }

  return Object.freeze({
    authority: `${parsed.origin}/${pathSegments.join("/")}`,
    knownAuthorities: Object.freeze([parsed.hostname]),
  });
}

export function loadFrontendConfig(env: EnvRecord): FrontendConfig {
  const apiBaseUrlValue = readString(env, "VITE_ECI_API_BASE_URL");
  const apiBaseUrlParsed = parseHttpUrl("VITE_ECI_API_BASE_URL", apiBaseUrlValue);
  const apiBaseUrl = `${apiBaseUrlParsed.origin}${apiBaseUrlParsed.pathname.replace(/\/+$/, "")}`;

  const entraSpaClientId = readString(env, "VITE_ENTRA_SPA_CLIENT_ID");
  if (!GUID.test(entraSpaClientId)) {
    throw new FrontendConfigError("VITE_ENTRA_SPA_CLIENT_ID is invalid.");
  }

  const entraRedirectUri = readString(env, "VITE_ENTRA_REDIRECT_URI");
  const redirectParsed = parseHttpUrl("VITE_ENTRA_REDIRECT_URI", entraRedirectUri);
  if (redirectParsed.search) {
    throw new FrontendConfigError("VITE_ENTRA_REDIRECT_URI is not a valid URL.");
  }

  const eciApiScopes = parseEciApiScopes(readString(env, "VITE_ECI_API_SCOPES"));
  const { authority: entraAuthority, knownAuthorities } = parseEntraAuthority(
    readString(env, "VITE_ENTRA_AUTHORITY"),
  );

  return Object.freeze({
    apiBaseUrl,
    entraSpaClientId,
    entraRedirectUri,
    eciApiScopes,
    entraAuthority,
    knownAuthorities,
  });
}
