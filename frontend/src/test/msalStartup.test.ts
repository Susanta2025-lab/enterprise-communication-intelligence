import {
  EventType,
  InteractionType,
  PublicClientApplication,
  type AccountInfo,
  type AuthenticationResult,
  type EventMessage,
  type IPublicClientApplication,
} from "@azure/msal-browser";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createMsalInstance, initializeMsal } from "../auth/msal";
import { sanitizeMsalError, scanAuthRedirectLocation } from "../auth/msalDiagnostics";
import { TEST_CONFIG } from "./fixtures";

function account(homeAccountId = "home-1"): AccountInfo {
  return {
    homeAccountId,
    localAccountId: "local-1",
    environment: "login.windows.net",
    tenantId: "11111111-1111-1111-1111-111111111111",
    username: "ada@example.com",
    name: "Ada Lovelace",
  };
}

function authEvent(
  eventType: (typeof EventType)[keyof typeof EventType],
  payload: EventMessage["payload"],
): EventMessage {
  return {
    eventType,
    interactionType: InteractionType.Redirect,
    payload,
    error: null,
    correlationId: "corr-1",
    timestamp: Date.now(),
  };
}

describe("scanAuthRedirectLocation", () => {
  it("detects auth params in the fragment without reading values for logs", () => {
    expect(
      scanAuthRedirectLocation({
        hash: "#code=authcode&state=xyz&client_info=abc",
        search: "",
      }),
    ).toEqual({ hasAuthParamsInHash: true, hasAuthParamsInQuery: false });
  });

  it("detects auth params in the query string", () => {
    expect(
      scanAuthRedirectLocation({
        hash: "",
        search: "?code=authcode&state=xyz&session_state=ss",
      }),
    ).toEqual({ hasAuthParamsInHash: false, hasAuthParamsInQuery: true });
  });

  it("ignores unrelated hash or query parameters", () => {
    expect(
      scanAuthRedirectLocation({
        hash: "#/mailbox/123",
        search: "?utm=1",
      }),
    ).toEqual({ hasAuthParamsInHash: false, hasAuthParamsInQuery: false });
  });
});

describe("sanitizeMsalError", () => {
  it("extracts errorCode, aadstsCode, and a short structured subError only", () => {
    const sanitized = sanitizeMsalError({
      name: "ServerError",
      errorCode: "invalid_resource",
      subError: "resource_disabled",
      errorMessage:
        "AADSTS650057: Invalid resource. The client has requested access to a resource which is not listed.",
      message:
        "invalid_resource: AADSTS650057: Invalid resource. Correlation ID: 11111111-1111-1111-1111-111111111111",
      correlationId: "11111111-1111-1111-1111-111111111111",
    });

    expect(sanitized).toEqual({
      errorName: "ServerError",
      errorCode: "invalid_resource",
      aadstsCode: "AADSTS650057",
      subError: "resource_disabled",
    });
    expect(JSON.stringify(sanitized)).not.toMatch(/Correlation ID|11111111|Invalid resource/);
  });

  it("reads AADSTS from message when errorMessage is absent", () => {
    expect(
      sanitizeMsalError({
        name: "ServerError",
        errorCode: "invalid_resource",
        message: "See docs. aadsts500011 occurred during redirect.",
      }),
    ).toEqual({
      errorName: "ServerError",
      errorCode: "invalid_resource",
      aadstsCode: "AADSTS500011",
    });
  });

  it("omits long or free-form subError values and never returns message bodies", () => {
    const sanitized = sanitizeMsalError({
      name: "ServerError",
      errorCode: "invalid_resource",
      subError: "this is a long free-form description that must not be logged",
      errorMessage: "AADSTS650057: https://login.microsoftonline.com/example/oauth2/v2.0/token",
    });

    expect(sanitized).toEqual({
      errorName: "ServerError",
      errorCode: "invalid_resource",
      aadstsCode: "AADSTS650057",
    });
    expect(sanitized).not.toHaveProperty("subError");
    expect(JSON.stringify(sanitized)).not.toMatch(/https:\/\/|free-form|oauth2/);
  });

  it("returns only a type tag for non-object errors", () => {
    expect(sanitizeMsalError("boom")).toEqual({ errorName: "string" });
    expect(sanitizeMsalError(null)).toEqual({ errorName: "object" });
  });
});

describe("initializeMsal startup", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("initializes the PCA without calling handleRedirectPromise", async () => {
    const cached = account();
    const instance = {
      initialize: vi.fn(async () => undefined),
      handleRedirectPromise: vi.fn(async () => null),
      getActiveAccount: vi.fn(() => null),
      getAllAccounts: vi.fn(() => [cached]),
      setActiveAccount: vi.fn(),
    };

    await initializeMsal(instance as unknown as IPublicClientApplication);

    expect(instance.initialize).toHaveBeenCalledTimes(1);
    expect(instance.handleRedirectPromise).not.toHaveBeenCalled();
    expect(instance.setActiveAccount).toHaveBeenCalledWith(cached);
  });

  it("prefers an existing active account over the first cached account", async () => {
    const active = account("active");
    const other = account("other");
    const instance = {
      initialize: vi.fn(async () => undefined),
      handleRedirectPromise: vi.fn(async () => null),
      getActiveAccount: vi.fn(() => active),
      getAllAccounts: vi.fn(() => [other, active]),
      setActiveAccount: vi.fn(),
    };

    await initializeMsal(instance as unknown as IPublicClientApplication);

    expect(instance.handleRedirectPromise).not.toHaveBeenCalled();
    expect(instance.setActiveAccount).toHaveBeenCalledWith(active);
  });

  it("does not set an active account when the cache is empty", async () => {
    const instance = {
      initialize: vi.fn(async () => undefined),
      handleRedirectPromise: vi.fn(async () => null),
      getActiveAccount: vi.fn(() => null),
      getAllAccounts: vi.fn(() => []),
      setActiveAccount: vi.fn(),
    };

    await initializeMsal(instance as unknown as IPublicClientApplication);

    expect(instance.handleRedirectPromise).not.toHaveBeenCalled();
    expect(instance.setActiveAccount).not.toHaveBeenCalled();
  });
});

describe("createMsalInstance active-account events", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("promotes LOGIN_SUCCESS and ACQUIRE_TOKEN_SUCCESS accounts via event callback", () => {
    const callbacks: Array<(message: EventMessage) => void> = [];
    vi.spyOn(PublicClientApplication.prototype, "addEventCallback").mockImplementation(
      (callback) => {
        callbacks.push(callback);
        return "cb-1";
      },
    );
    const setActiveAccount = vi
      .spyOn(PublicClientApplication.prototype, "setActiveAccount")
      .mockImplementation(() => undefined);

    createMsalInstance(TEST_CONFIG);
    expect(callbacks).toHaveLength(1);

    const signedIn = account();
    callbacks[0]?.(authEvent(EventType.LOGIN_SUCCESS, signedIn));
    expect(setActiveAccount).toHaveBeenCalledWith(signedIn);

    const result = {
      account: account("from-token"),
    } as AuthenticationResult;
    callbacks[0]?.(authEvent(EventType.ACQUIRE_TOKEN_SUCCESS, result));
    expect(setActiveAccount).toHaveBeenCalledWith(result.account);
  });
});
