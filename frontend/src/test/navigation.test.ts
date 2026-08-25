import { describe, expect, it } from "vitest";

import { isSafeAuthorizationUrl, navigateToAuthorizationUrl } from "../navigation/external";

describe("authorization URL navigation", () => {
  it("accepts https provider authorization URLs", () => {
    expect(isSafeAuthorizationUrl("https://accounts.google.com/o/oauth2/v2/auth?client_id=x")).toBe(
      true,
    );
    expect(
      isSafeAuthorizationUrl("https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"),
    ).toBe(true);
  });

  it("rejects javascript, data, http, and userinfo URLs", () => {
    expect(isSafeAuthorizationUrl("javascript:alert(1)")).toBe(false);
    expect(isSafeAuthorizationUrl("http://evil.example/phish")).toBe(false);
    expect(isSafeAuthorizationUrl("https://user:pass@accounts.google.com/")).toBe(false);
    expect(isSafeAuthorizationUrl("/relative")).toBe(false);
  });

  it("does not navigate to an unsafe URL", () => {
    expect(navigateToAuthorizationUrl("javascript:alert(1)")).toBe(false);
    expect(navigateToAuthorizationUrl("http://evil.example/phish")).toBe(false);
  });
});
