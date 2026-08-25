export const OAUTH_OUTCOMES = [
  "success",
  "denied",
  "expired",
  "identity_mismatch",
  "failed",
] as const;

export type OAuthOutcome = (typeof OAUTH_OUTCOMES)[number];

export const OAUTH_PROVIDERS = ["gmail", "microsoft_graph"] as const;

export type OAuthProvider = (typeof OAUTH_PROVIDERS)[number];

export type OAuthReturnResult = {
  oauth: OAuthOutcome | "unknown";
  provider: OAuthProvider | null;
  shouldRefresh: boolean;
};

const OUTCOME_SET = new Set<string>(OAUTH_OUTCOMES);
const PROVIDER_SET = new Set<string>(OAUTH_PROVIDERS);

export function parseOAuthReturnSearch(search: string): OAuthReturnResult | null {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const oauthRaw = params.get("oauth");
  const providerRaw = params.get("provider");
  if (oauthRaw === null && providerRaw === null) {
    return null;
  }
  const oauth = oauthRaw && OUTCOME_SET.has(oauthRaw) ? (oauthRaw as OAuthOutcome) : "unknown";
  const provider =
    providerRaw && PROVIDER_SET.has(providerRaw) ? (providerRaw as OAuthProvider) : null;
  return {
    oauth,
    provider,
    shouldRefresh: oauth === "success" || oauth === "unknown" || oauth === "failed",
  };
}

export function stripOAuthReturnParams(search: string): string {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  params.delete("oauth");
  params.delete("provider");
  const next = params.toString();
  return next ? `?${next}` : "";
}

export function oauthReturnMessage(result: OAuthReturnResult): { tone: "success" | "error"; text: string } {
  if (result.oauth === "success") {
    return {
      tone: "success",
      text:
        result.provider === "microsoft_graph"
          ? "Mailbox connected. Microsoft Outlook authorization completed."
          : "Mailbox connected.",
    };
  }
  if (result.oauth === "denied") {
    return {
      tone: "error",
      text: "Mailbox consent was not completed. The connection is unchanged.",
    };
  }
  if (result.oauth === "expired") {
    return {
      tone: "error",
      text: "The authorization session expired. Try connecting again.",
    };
  }
  if (result.oauth === "identity_mismatch") {
    return {
      tone: "error",
      text: "Reauthorization must use the same mailbox account. The existing connection was preserved.",
    };
  }
  if (result.oauth === "failed") {
    return {
      tone: "error",
      text: "Mailbox connection failed. Try again.",
    };
  }
  return {
    tone: "error",
    text: "Mailbox connection status is unavailable.",
  };
}
