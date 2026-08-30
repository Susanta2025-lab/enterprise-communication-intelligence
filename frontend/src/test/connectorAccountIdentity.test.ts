import { describe, expect, it } from "vitest";

import {
  ACCOUNT_IDENTITY_UNAVAILABLE,
  CONNECT_ANOTHER_ACCOUNT_UNAVAILABLE_REASON,
  ConnectAnotherAccountUnavailableError,
  connectAnotherAccountAvailability,
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
  it("is unavailable until a backend account-selection contract exists", () => {
    expect(connectAnotherAccountAvailability("gmail")).toEqual({
      supported: false,
      reason: CONNECT_ANOTHER_ACCOUNT_UNAVAILABLE_REASON,
    });
    expect(() =>
      startConnectAnotherAccount({ provider: "gmail", intent: "connect_another_account" }),
    ).toThrow(ConnectAnotherAccountUnavailableError);
  });
});
