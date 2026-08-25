import { describe, expect, it } from "vitest";

import {
  ECI_PERMISSIONS,
  hasAllPermissions,
  hasPermission,
  parseScopeClaim,
} from "../auth/permissions";

describe("ECI permission helpers", () => {
  it("parses exact communications:* names from scp", () => {
    const scp = ECI_PERMISSIONS.join(" ");
    expect(parseScopeClaim(scp)).toEqual([...ECI_PERMISSIONS]);
  });

  it("parses full scope identifiers down to communications:* names", () => {
    expect(
      parseScopeClaim("api://33333333-3333-3333-3333-333333333333/communications:analyze"),
    ).toEqual(["communications:analyze"]);
  });

  it("ignores unknown and dot-separated names", () => {
    expect(parseScopeClaim("communications.read openid profile")).toEqual([]);
  });

  it("treats missing scp as no permissions", () => {
    expect(parseScopeClaim(undefined)).toEqual([]);
    expect(parseScopeClaim("")).toEqual([]);
  });

  it("hasPermission matches a required communications:* permission", () => {
    const permissions = ["communications:read", "communications:analyze"];
    expect(hasPermission(permissions, "communications:analyze")).toBe(true);
    expect(hasPermission(permissions, "communications:send")).toBe(false);
  });

  it("hasAllPermissions requires every listed permission", () => {
    const permissions = [
      "communications:read",
      "communications:analyze",
      "communications:connect",
    ];
    expect(
      hasAllPermissions(permissions, ["communications:read", "communications:analyze"]),
    ).toBe(true);
    expect(
      hasAllPermissions(permissions, ["communications:read", "communications:send"]),
    ).toBe(false);
  });

  it("does not treat missing scopes as granted", () => {
    expect(hasAllPermissions([], [...ECI_PERMISSIONS])).toBe(false);
  });
});
