import { describe, expect, it } from "vitest";

import {
  FrontendConfigError,
  loadFrontendConfig,
  parseEciApiScopes,
  parseEntraAuthority,
} from "../config/env";
import { TEST_ENV } from "./fixtures";

describe("frontend configuration", () => {
  it("loads and freezes valid public configuration", () => {
    const config = loadFrontendConfig(TEST_ENV);
    expect(config.apiBaseUrl).toBe("http://localhost:8000");
    expect(config.entraAuthority).toBe(
      "https://example.ciamlogin.com/11111111-1111-1111-1111-111111111111",
    );
    expect(config.knownAuthorities).toEqual(["example.ciamlogin.com"]);
    expect(config.entraRedirectUri).toBe("http://localhost:5173");
    expect(config.eciApiScopes).toEqual([
      "api://33333333-3333-3333-3333-333333333333/communications:read",
      "api://33333333-3333-3333-3333-333333333333/communications:analyze",
      "api://33333333-3333-3333-3333-333333333333/communications:connect",
      "api://33333333-3333-3333-3333-333333333333/communications:workflow",
      "api://33333333-3333-3333-3333-333333333333/communications:send",
    ]);
    expect(Object.isFrozen(config)).toBe(true);
  });

  it("accepts an explicit CIAM authority and derives knownAuthorities from its hostname", () => {
    const parsed = parseEntraAuthority(
      "https://example.ciamlogin.com/11111111-1111-1111-1111-111111111111/",
    );
    expect(parsed.authority).toBe(
      "https://example.ciamlogin.com/11111111-1111-1111-1111-111111111111",
    );
    expect(parsed.knownAuthorities).toEqual(["example.ciamlogin.com"]);
  });

  it("does not derive product-login authority from a workforce tenant id", () => {
    const config = loadFrontendConfig({
      ...TEST_ENV,
      VITE_ENTRA_AUTHORITY: "https://example.ciamlogin.com/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      VITE_ENTRA_TENANT_ID: "99999999-9999-9999-9999-999999999999",
    });
    expect(config.entraAuthority).toBe(
      "https://example.ciamlogin.com/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    );
    expect(config.entraAuthority).not.toContain("login.microsoftonline.com");
    expect(config).not.toHaveProperty("entraTenantId");
  });

  it("parses comma or whitespace separated explicit scopes", () => {
    const scopes = parseEciApiScopes(
      "api://33333333-3333-3333-3333-333333333333/communications:read api://33333333-3333-3333-3333-333333333333/communications:analyze",
    );
    expect(scopes).toHaveLength(2);
  });

  it.each([
    "VITE_ECI_API_BASE_URL",
    "VITE_ENTRA_AUTHORITY",
    "VITE_ENTRA_SPA_CLIENT_ID",
    "VITE_ENTRA_REDIRECT_URI",
    "VITE_ECI_API_SCOPES",
  ])("rejects missing %s", (key) => {
    expect(() => loadFrontendConfig({ ...TEST_ENV, [key]: "" })).toThrow(FrontendConfigError);
    expect(() => loadFrontendConfig({ ...TEST_ENV, [key]: undefined })).toThrow(
      FrontendConfigError,
    );
  });

  it.each([
    ["not-a-url", "VITE_ENTRA_AUTHORITY is not a valid URL."],
    ["http://example.ciamlogin.com/11111111-1111-1111-1111-111111111111", "must be an https URL"],
    ["https://localhost/11111111-1111-1111-1111-111111111111", "hostname is invalid"],
    ["https://127.0.0.1/11111111-1111-1111-1111-111111111111", "hostname is invalid"],
    ["https://example.ciamlogin.com", "must include a tenant path"],
    ["https://example.ciamlogin.com/", "must include a tenant path"],
    ["https://example.ciamlogin.com/11111111-1111-1111-1111-111111111111?foo=1", "is not a valid URL"],
    [
      "https://user:pass@example.ciamlogin.com/11111111-1111-1111-1111-111111111111",
      "is not a valid URL",
    ],
  ])("rejects malformed authority %s", (authority, message) => {
    expect(() => loadFrontendConfig({ ...TEST_ENV, VITE_ENTRA_AUTHORITY: authority })).toThrow(
      FrontendConfigError,
    );
    expect(() => loadFrontendConfig({ ...TEST_ENV, VITE_ENTRA_AUTHORITY: authority })).toThrow(
      message,
    );
  });

  it("rejects empty scope lists", () => {
    expect(() => parseEciApiScopes("   ")).toThrow(FrontendConfigError);
  });

  it("rejects .default as the browser permission strategy", () => {
    expect(() =>
      parseEciApiScopes("api://33333333-3333-3333-3333-333333333333/.default"),
    ).toThrow(FrontendConfigError);
  });

  it("rejects dot-separated permission replacements", () => {
    expect(() =>
      parseEciApiScopes("api://33333333-3333-3333-3333-333333333333/communications.read"),
    ).toThrow(FrontendConfigError);
  });

  it("rejects scopes that are not full identifiers", () => {
    expect(() => parseEciApiScopes("communications:read")).toThrow(FrontendConfigError);
  });
});
