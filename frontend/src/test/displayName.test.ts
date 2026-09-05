import type { AccountInfo } from "@azure/msal-browser";
import { describe, expect, it } from "vitest";

import { resolveDisplayName } from "../auth/displayName";

function account(overrides: Partial<AccountInfo> = {}): AccountInfo {
  return {
    homeAccountId: "home-account-1",
    localAccountId: "local-account-1",
    environment: "example.ciamlogin.com",
    tenantId: "11111111-1111-1111-1111-111111111111",
    username: "ada@example.com",
    name: "Ada Lovelace",
    ...overrides,
  };
}

describe("resolveDisplayName", () => {
  it("prefers a real account name", () => {
    expect(resolveDisplayName(account())).toBe("Ada Lovelace");
  });

  it("ignores External ID placeholder names and uses username", () => {
    expect(resolveDisplayName(account({ name: "unknown" }))).toBe("ada@example.com");
    expect(resolveDisplayName(account({ name: "Unknown" }))).toBe("ada@example.com");
  });

  it("returns null when name and username are placeholders or empty", () => {
    expect(resolveDisplayName(account({ name: "unknown", username: "unknown" }))).toBeNull();
    expect(resolveDisplayName(account({ name: "  ", username: "" }))).toBeNull();
    expect(resolveDisplayName(null)).toBeNull();
  });
});
