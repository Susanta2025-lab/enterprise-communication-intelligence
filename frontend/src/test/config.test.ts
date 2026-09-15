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
    expect(config.cloudProvider).toBe("azure");
    expect(config.aiProvider).toBe("microsoft_foundry");
    expect(config.cloudRegion).toBe("Spain Central");
    expect(Object.isFrozen(config)).toBe(true);
  });

  it("parses a valid Azure deployment configuration", () => {
    const config = loadFrontendConfig({
      ...TEST_ENV,
      VITE_ECI_CLOUD_PROVIDER: "azure",
      VITE_ECI_AI_PROVIDER: "microsoft_foundry",
      VITE_ECI_CLOUD_REGION: "Spain Central",
    });
    expect(config.cloudProvider).toBe("azure");
    expect(config.aiProvider).toBe("microsoft_foundry");
    expect(config.cloudRegion).toBe("Spain Central");
  });

  it("parses a valid AWS deployment configuration", () => {
    const config = loadFrontendConfig({
      ...TEST_ENV,
      VITE_ECI_CLOUD_PROVIDER: "aws",
      VITE_ECI_AI_PROVIDER: "amazon_bedrock",
      VITE_ECI_CLOUD_REGION: "eu-south-2",
    });
    expect(config.cloudProvider).toBe("aws");
    expect(config.aiProvider).toBe("amazon_bedrock");
    expect(config.cloudRegion).toBe("eu-south-2");
  });

  it("fails closed for an unsupported cloud provider", () => {
    expect(() =>
      loadFrontendConfig({ ...TEST_ENV, VITE_ECI_CLOUD_PROVIDER: "gcp" }),
    ).toThrow(FrontendConfigError);
    expect(() =>
      loadFrontendConfig({ ...TEST_ENV, VITE_ECI_CLOUD_PROVIDER: "gcp" }),
    ).toThrow("VITE_ECI_CLOUD_PROVIDER must be azure or aws");
  });

  it("fails closed for an unsupported AI provider", () => {
    expect(() =>
      loadFrontendConfig({ ...TEST_ENV, VITE_ECI_AI_PROVIDER: "openai" }),
    ).toThrow(FrontendConfigError);
    expect(() =>
      loadFrontendConfig({ ...TEST_ENV, VITE_ECI_AI_PROVIDER: "openai" }),
    ).toThrow("VITE_ECI_AI_PROVIDER must be microsoft_foundry or amazon_bedrock");
  });

  it("fails closed for an invalid cloud and AI provider combination", () => {
    expect(() =>
      loadFrontendConfig({
        ...TEST_ENV,
        VITE_ECI_CLOUD_PROVIDER: "aws",
        VITE_ECI_AI_PROVIDER: "microsoft_foundry",
        VITE_ECI_CLOUD_REGION: "eu-south-2",
      }),
    ).toThrow(FrontendConfigError);
    expect(() =>
      loadFrontendConfig({
        ...TEST_ENV,
        VITE_ECI_CLOUD_PROVIDER: "azure",
        VITE_ECI_AI_PROVIDER: "amazon_bedrock",
        VITE_ECI_CLOUD_REGION: "Spain Central",
      }),
    ).toThrow("supported deployment combination");
  });

  it("fails closed for an unsupported region label", () => {
    expect(() =>
      loadFrontendConfig({
        ...TEST_ENV,
        VITE_ECI_CLOUD_PROVIDER: "azure",
        VITE_ECI_AI_PROVIDER: "microsoft_foundry",
        VITE_ECI_CLOUD_REGION: "West Europe",
      }),
    ).toThrow("supported deployment combination");
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
      [
        "api://33333333-3333-3333-3333-333333333333/communications:read",
        "api://33333333-3333-3333-3333-333333333333/communications:analyze",
        "api://33333333-3333-3333-3333-333333333333/communications:connect",
        "api://33333333-3333-3333-3333-333333333333/communications:workflow",
        "api://33333333-3333-3333-3333-333333333333/communications:send",
      ].join(" "),
    );
    expect(scopes).toHaveLength(5);
  });

  it.each([
    "VITE_ECI_API_BASE_URL",
    "VITE_ENTRA_AUTHORITY",
    "VITE_ENTRA_SPA_CLIENT_ID",
    "VITE_ENTRA_REDIRECT_URI",
    "VITE_ECI_API_SCOPES",
    "VITE_ECI_CLOUD_PROVIDER",
    "VITE_ECI_AI_PROVIDER",
    "VITE_ECI_CLOUD_REGION",
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
      parseEciApiScopes(
        [
          "api://33333333-3333-3333-3333-333333333333/.default",
          "api://33333333-3333-3333-3333-333333333333/communications:analyze",
          "api://33333333-3333-3333-3333-333333333333/communications:connect",
          "api://33333333-3333-3333-3333-333333333333/communications:workflow",
          "api://33333333-3333-3333-3333-333333333333/communications:send",
        ].join(","),
      ),
    ).toThrow("not .default");
  });

  it("rejects dot-separated permission replacements", () => {
    expect(() =>
      parseEciApiScopes(
        [
          "api://33333333-3333-3333-3333-333333333333/communications.read",
          "api://33333333-3333-3333-3333-333333333333/communications:analyze",
          "api://33333333-3333-3333-3333-333333333333/communications:connect",
          "api://33333333-3333-3333-3333-333333333333/communications:workflow",
          "api://33333333-3333-3333-3333-333333333333/communications:send",
        ].join(","),
      ),
    ).toThrow("exact communications:* permission names");
  });

  it("rejects scopes that are not full identifiers", () => {
    expect(() =>
      parseEciApiScopes(
        [
          "communications:read",
          "api://33333333-3333-3333-3333-333333333333/communications:analyze",
          "api://33333333-3333-3333-3333-333333333333/communications:connect",
          "api://33333333-3333-3333-3333-333333333333/communications:workflow",
          "api://33333333-3333-3333-3333-333333333333/communications:send",
        ].join(","),
      ),
    ).toThrow("full ECI scope identifiers");
  });

  it("rejects nested permission paths such as /communications:send/communications:read", () => {
    const nested = [
      "api://33333333-3333-3333-3333-333333333333/communications:send/communications:read",
      "api://33333333-3333-3333-3333-333333333333/communications:send/communications:analyze",
      "api://33333333-3333-3333-3333-333333333333/communications:send/communications:connect",
      "api://33333333-3333-3333-3333-333333333333/communications:send/communications:workflow",
      "api://33333333-3333-3333-3333-333333333333/communications:send/communications:send",
    ].join(" ");
    expect(() => parseEciApiScopes(nested)).toThrow(FrontendConfigError);
    expect(() => parseEciApiScopes(nested)).toThrow(
      "must use a single permission path segment per scope",
    );
  });

  it("rejects fewer than five scopes even when each path is well-formed", () => {
    expect(() =>
      parseEciApiScopes(
        "api://33333333-3333-3333-3333-333333333333/communications:read api://33333333-3333-3333-3333-333333333333/communications:analyze",
      ),
    ).toThrow("exactly 5 delegated scopes");
  });

  it("rejects mixed api:// resource prefixes", () => {
    expect(() =>
      parseEciApiScopes(
        [
          "api://33333333-3333-3333-3333-333333333333/communications:read",
          "api://44444444-4444-4444-4444-444444444444/communications:analyze",
          "api://33333333-3333-3333-3333-333333333333/communications:connect",
          "api://33333333-3333-3333-3333-333333333333/communications:workflow",
          "api://33333333-3333-3333-3333-333333333333/communications:send",
        ].join(","),
      ),
    ).toThrow("one shared api:// resource prefix");
  });

  it("rejects a five-scope list that omits one required permission", () => {
    expect(() =>
      parseEciApiScopes(
        [
          "api://33333333-3333-3333-3333-333333333333/communications:read",
          "api://33333333-3333-3333-3333-333333333333/communications:analyze",
          "api://33333333-3333-3333-3333-333333333333/communications:connect",
          "api://33333333-3333-3333-3333-333333333333/communications:workflow",
          "api://33333333-3333-3333-3333-333333333333/communications:workflow",
        ].join(","),
      ),
    ).toThrow("duplicate permissions");
  });
});
