import { describe, expect, it } from "vitest";

import { createMsalConfiguration } from "../auth/msal";
import { TEST_CONFIG } from "./fixtures";

describe("MSAL configuration", () => {
  it("configures a public SPA client with sessionStorage and no secret fields", () => {
    const configuration = createMsalConfiguration(TEST_CONFIG);
    expect(configuration.auth?.clientId).toBe(TEST_CONFIG.entraSpaClientId);
    expect(configuration.auth?.authority).toBe(TEST_CONFIG.entraAuthority);
    expect(configuration.auth?.redirectUri).toBe(TEST_CONFIG.entraRedirectUri);
    expect(configuration.cache?.cacheLocation).toBe("sessionStorage");
    expect(JSON.stringify(configuration)).not.toMatch(/clientSecret|client_secret/);
  });
});
