import { ECI_PERMISSIONS, isEciPermission } from "../auth/permissions";

export type EnvRecord = Record<string, string | boolean | undefined>;

/** Build-time cloud host for presentation only. Not an authorization input. */
export type CloudProvider = "azure" | "aws";

/** Build-time AI backend for presentation only. Not an authorization input. */
export type AiProvider = "microsoft_foundry" | "amazon_bedrock";

export type FrontendConfig = {
  readonly apiBaseUrl: string;
  readonly entraSpaClientId: string;
  readonly entraRedirectUri: string;
  readonly eciApiScopes: readonly string[];
  readonly entraAuthority: string;
  readonly knownAuthorities: readonly string[];
  /** Public build-time presentation metadata. Not credentials or owner identity. */
  readonly cloudProvider: CloudProvider;
  /** Public build-time presentation metadata. Not credentials or owner identity. */
  readonly aiProvider: AiProvider;
  /** Safe display region label only. Not an infrastructure identifier beyond the label. */
  readonly cloudRegion: string;
};

const CLOUD_PROVIDERS = new Set<CloudProvider>(["azure", "aws"]);
const AI_PROVIDERS = new Set<AiProvider>(["microsoft_foundry", "amazon_bedrock"]);

/** Allowed cloud ↔ AI ↔ region combinations. Fail closed on any other pairing. */
const DEPLOYMENT_COMBINATIONS: ReadonlyArray<{
  readonly cloudProvider: CloudProvider;
  readonly aiProvider: AiProvider;
  readonly cloudRegion: string;
}> = [
  {
    cloudProvider: "azure",
    aiProvider: "microsoft_foundry",
    cloudRegion: "Spain Central",
  },
  {
    cloudProvider: "aws",
    aiProvider: "amazon_bedrock",
    cloudRegion: "eu-south-2",
  },
];

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
  if (parts.length !== ECI_PERMISSIONS.length) {
    throw new FrontendConfigError(
      `VITE_ECI_API_SCOPES must contain exactly ${ECI_PERMISSIONS.length} delegated scopes.`,
    );
  }

  const seen = new Set<string>();
  let resourcePrefix: string | null = null;
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
      if (!url.hostname) {
        throw new FrontendConfigError(
          "VITE_ECI_API_SCOPES must contain full ECI scope identifiers.",
        );
      }
      const pathSegments = url.pathname.split("/").filter(Boolean);
      // Reject nested paths such as /communications:send/communications:read.
      if (pathSegments.length !== 1) {
        throw new FrontendConfigError(
          "VITE_ECI_API_SCOPES must use a single permission path segment per scope.",
        );
      }
      permission = pathSegments[0] ?? "";
      const prefix = `api://${url.hostname}`.toLowerCase();
      if (resourcePrefix === null) {
        resourcePrefix = prefix;
      } else if (prefix !== resourcePrefix) {
        throw new FrontendConfigError(
          "VITE_ECI_API_SCOPES must use one shared api:// resource prefix.",
        );
      }
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

  for (const required of ECI_PERMISSIONS) {
    if (!seen.has(required)) {
      throw new FrontendConfigError(
        "VITE_ECI_API_SCOPES must include each communications:* permission exactly once.",
      );
    }
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

function parseCloudProvider(raw: string): CloudProvider {
  if (!CLOUD_PROVIDERS.has(raw as CloudProvider)) {
    throw new FrontendConfigError(
      "VITE_ECI_CLOUD_PROVIDER must be azure or aws.",
    );
  }
  return raw as CloudProvider;
}

function parseAiProvider(raw: string): AiProvider {
  if (!AI_PROVIDERS.has(raw as AiProvider)) {
    throw new FrontendConfigError(
      "VITE_ECI_AI_PROVIDER must be microsoft_foundry or amazon_bedrock.",
    );
  }
  return raw as AiProvider;
}

function parseDeploymentMetadata(env: EnvRecord): {
  readonly cloudProvider: CloudProvider;
  readonly aiProvider: AiProvider;
  readonly cloudRegion: string;
} {
  const cloudProvider = parseCloudProvider(readString(env, "VITE_ECI_CLOUD_PROVIDER"));
  const aiProvider = parseAiProvider(readString(env, "VITE_ECI_AI_PROVIDER"));
  const cloudRegion = readString(env, "VITE_ECI_CLOUD_REGION");

  const allowed = DEPLOYMENT_COMBINATIONS.some(
    (combo) =>
      combo.cloudProvider === cloudProvider &&
      combo.aiProvider === aiProvider &&
      combo.cloudRegion === cloudRegion,
  );
  if (!allowed) {
    throw new FrontendConfigError(
      "VITE_ECI_CLOUD_PROVIDER, VITE_ECI_AI_PROVIDER, and VITE_ECI_CLOUD_REGION must form a supported deployment combination.",
    );
  }

  return Object.freeze({ cloudProvider, aiProvider, cloudRegion });
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
  const deployment = parseDeploymentMetadata(env);

  return Object.freeze({
    apiBaseUrl,
    entraSpaClientId,
    entraRedirectUri,
    eciApiScopes,
    entraAuthority,
    knownAuthorities,
    cloudProvider: deployment.cloudProvider,
    aiProvider: deployment.aiProvider,
    cloudRegion: deployment.cloudRegion,
  });
}
