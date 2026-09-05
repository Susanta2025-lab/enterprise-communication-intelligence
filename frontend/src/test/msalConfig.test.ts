import { describe, expect, it } from "vitest";

import { buildLoginRequest, buildLogoutRequest, createMsalConfiguration } from "../auth/msal";
import { TEST_CONFIG } from "./fixtures";

describe("MSAL configuration", () => {
  it("configures a public SPA client with sessionStorage and no secret fields", () => {
    const configuration = createMsalConfiguration(TEST_CONFIG);
    expect(configuration.auth?.clientId).toBe(TEST_CONFIG.entraSpaClientId);
    expect(configuration.auth?.authority).toBe(TEST_CONFIG.entraAuthority);
    expect(configuration.auth?.knownAuthorities).toEqual(["example.ciamlogin.com"]);
    expect(configuration.auth?.redirectUri).toBe(TEST_CONFIG.entraRedirectUri);
    expect(configuration.auth?.postLogoutRedirectUri).toBe(TEST_CONFIG.entraRedirectUri);
    expect(configuration.cache?.cacheLocation).toBe("sessionStorage");
    expect(JSON.stringify(configuration)).not.toMatch(/clientSecret|client_secret/);
  });

  it("uses the configured CIAM authority instead of a workforce login host", () => {
    const configuration = createMsalConfiguration(TEST_CONFIG);
    expect(configuration.auth?.authority).toBe(
      "https://example.ciamlogin.com/11111111-1111-1111-1111-111111111111",
    );
    expect(configuration.auth?.authority).not.toMatch(
      /^https:\/\/login\.microsoftonline\.com\//,
    );
    expect(configuration.auth?.knownAuthorities).toContain(
      new URL(TEST_CONFIG.entraAuthority).hostname,
    );
  });

  it("keeps login and logout on the same frontend redirect URI and ECI scopes", () => {
    const loginRequest = buildLoginRequest(TEST_CONFIG);
    const logoutRequest = buildLogoutRequest(TEST_CONFIG, null);
    expect(loginRequest.redirectUri).toBe(TEST_CONFIG.entraRedirectUri);
    expect(loginRequest.scopes).toEqual([
      "api://33333333-3333-3333-3333-333333333333/communications:read",
      "api://33333333-3333-3333-3333-333333333333/communications:analyze",
      "api://33333333-3333-3333-3333-333333333333/communications:connect",
      "api://33333333-3333-3333-3333-333333333333/communications:workflow",
      "api://33333333-3333-3333-3333-333333333333/communications:send",
    ]);
    expect(loginRequest.scopes?.join(" ")).not.toMatch(/Mail\.(Read|Send)|https:\/\/www\.googleapis\.com/);
    expect(logoutRequest.postLogoutRedirectUri).toBe(TEST_CONFIG.entraRedirectUri);
    expect(logoutRequest.account).toBeUndefined();
  });
});
