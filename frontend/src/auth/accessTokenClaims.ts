import { parseScopeClaim, type EciPermission } from "./permissions";

export function scopeClaimFromAccessToken(token: string): string {
  const parts = token.split(".");
  if (parts.length < 2 || !parts[1]) {
    return "";
  }
  try {
    const json = utf8FromBase64Url(parts[1]);
    const payload = JSON.parse(json) as { scp?: unknown; scope?: unknown };
    if (typeof payload.scp === "string") {
      return payload.scp;
    }
    if (typeof payload.scope === "string") {
      return payload.scope;
    }
    return "";
  } catch {
    return "";
  }
}

export function permissionsFromAccessToken(token: string): readonly EciPermission[] {
  return parseScopeClaim(scopeClaimFromAccessToken(token));
}

function utf8FromBase64Url(value: string): string {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  return new TextDecoder().decode(Uint8Array.from(atob(padded), (char) => char.charCodeAt(0)));
}
