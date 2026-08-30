import { describe, expect, it } from "vitest";

import {
  ACCOUNT_IDENTITY_UNAVAILABLE,
  ConnectAnotherAccountUnavailableError,
  connectAnotherAccountAvailability,
  connectAnotherAccountAuthorizePath,
  connectorAccountReauthorizePath,
  connectorDisplayIdentity,
  startConnectAnotherAccount,
} from "../api/connectorAccounts";

describe("connector account identity", () => {
  it("uses the optional display_identity when present", () => {
    expect(connectorDisplayIdentity({ display_identity: "ops.mailbox@contoso.example" })).toBe(
      "ops.mailbox@contoso.example",
    );
  });

  it("renders a neutral placeholder instead of fabricating an address", () => {
    expect(connectorDisplayIdentity({})).toBe(ACCOUNT_IDENTITY_UNAVAILABLE);
    expect(connectorDisplayIdentity({ display_identity: null })).toBe(ACCOUNT_IDENTITY_UNAVAILABLE);
    expect(connectorDisplayIdentity({ display_identity: "" })).toBe(ACCOUNT_IDENTITY_UNAVAILABLE);
    expect(connectorDisplayIdentity({ display_identity: "   " })).toBe(ACCOUNT_IDENTITY_UNAVAILABLE);
  });
});

describe("connect-another account contract", () => {
  it("is enabled through the account-selection backend contract", () => {
    expect(connectAnotherAccountAvailability("gmail")).toEqual({ supported: true });
    expect(connectAnotherAccountAvailability("microsoft_graph")).toEqual({ supported: true });
    expect(startConnectAnotherAccount({ provider: "gmail", intent: "connect_another_account" })).toEqual(
      { path: "/api/v1/connector-accounts/gmail/authorize/another" },
    );
    expect(
      startConnectAnotherAccount({
        provider: "microsoft_graph",
        intent: "connect_another_account",
      }),
    ).toEqual({ path: "/api/v1/connector-accounts/microsoft_graph/authorize/another" });
    expect(connectAnotherAccountAuthorizePath("gmail")).not.toContain("/reauthorize");
    expect(connectAnotherAccountAuthorizePath("gmail")).not.toBe(
      "/api/v1/connector-accounts/gmail/authorize",
    );
    expect(connectorAccountReauthorizePath("11111111-1111-4111-8111-111111111111")).toContain(
      "/reauthorize",
    );
    expect(() =>
      startConnectAnotherAccount({
        provider: "gmail",
        intent: "connect_another_account",
      }),
    ).not.toThrow(ConnectAnotherAccountUnavailableError);
  });
});
