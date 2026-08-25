import { describe, expect, it } from "vitest";

import { FrontendConfigError, loadFrontendConfig, parseEciApiScopes } from "../config/env";
import { TEST_ENV } from "./fixtures";

describe("frontend configuration", () => {
  it("loads and freezes valid public configuration", () => {
    const config = loadFrontendConfig(TEST_ENV);
    expect(config.apiBaseUrl).toBe("http://localhost:8000");
    expect(config.entraAuthority).toBe(
      "https://login.microsoftonline.com/11111111-1111-1111-1111-111111111111",
    );
    expect(config.eciApiScopes).toEqual([
      "api://33333333-3333-3333-3333-333333333333/communications:read",
      "api://33333333-3333-3333-3333-333333333333/communications:analyze",
      "api://33333333-3333-3333-3333-333333333333/communications:connect",
      "api://33333333-3333-3333-3333-333333333333/communications:workflow",
      "api://33333333-3333-3333-3333-333333333333/communications:send",
    ]);
    expect(Object.isFrozen(config)).toBe(true);
  });

  it("parses comma or whitespace separated explicit scopes", () => {
    const scopes = parseEciApiScopes(
      "api://33333333-3333-3333-3333-333333333333/communications:read api://33333333-3333-3333-3333-333333333333/communications:analyze",
    );
    expect(scopes).toHaveLength(2);
  });

  it.each([
    "VITE_ECI_API_BASE_URL",
    "VITE_ENTRA_TENANT_ID",
    "VITE_ENTRA_SPA_CLIENT_ID",
    "VITE_ENTRA_REDIRECT_URI",
    "VITE_ECI_API_SCOPES",
  ])("rejects missing %s", (key) => {
    expect(() => loadFrontendConfig({ ...TEST_ENV, [key]: "" })).toThrow(FrontendConfigError);
    expect(() => loadFrontendConfig({ ...TEST_ENV, [key]: undefined })).toThrow(
      FrontendConfigError,
    );
  });

  it("rejects a malformed tenant id", () => {
    expect(() =>
      loadFrontendConfig({ ...TEST_ENV, VITE_ENTRA_TENANT_ID: "not-a-guid" }),
    ).toThrow(FrontendConfigError);
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
