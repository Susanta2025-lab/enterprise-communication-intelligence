import { describe, expect, it } from "vitest";

import { permissionsFromAccessToken, scopeClaimFromAccessToken } from "../auth/accessTokenClaims";

function tokenWithPayload(payload: Record<string, unknown>): string {
  const json = btoa(JSON.stringify(payload)).replaceAll("=", "").replaceAll("+", "-").replaceAll("/", "_");
  return `header.${json}.sig`;
}

describe("access token claims", () => {
  it("parses scp without logging or exposing the token", () => {
    const token = tokenWithPayload({
      scp: "communications:read communications:connect",
    });
    expect(scopeClaimFromAccessToken(token)).toBe("communications:read communications:connect");
    expect(permissionsFromAccessToken(token)).toEqual(["communications:read", "communications:connect"]);
  });

  it("returns no permissions for malformed tokens", () => {
    expect(permissionsFromAccessToken("not-a-jwt")).toEqual([]);
    expect(permissionsFromAccessToken("a.%%%")).toEqual([]);
  });
});
