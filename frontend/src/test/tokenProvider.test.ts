import {
  InteractionRequiredAuthError,
  type AccountInfo,
  type AuthenticationResult,
  type IPublicClientApplication,
} from "@azure/msal-browser";
import { describe, expect, it, vi } from "vitest";

import { InteractionRequiredError, MsalAccessTokenProvider } from "../auth/tokenProvider";
import { TEST_CONFIG, TEST_TOKEN } from "./fixtures";

function createMsalStub(overrides: Partial<IPublicClientApplication> = {}): IPublicClientApplication {
  return {
    getActiveAccount: vi.fn(() => null),
    getAllAccounts: vi.fn(() => []),
    acquireTokenSilent: vi.fn(),
    ...overrides,
  } as IPublicClientApplication;
}

describe("MSAL token provider", () => {
  it("returns a silent ECI access token", async () => {
    const account = { homeAccountId: "account-1" } as AccountInfo;
    const instance = createMsalStub({
      getActiveAccount: vi.fn(() => account),
      acquireTokenSilent: vi.fn(async () => ({ accessToken: TEST_TOKEN }) as AuthenticationResult),
    });
    const provider = new MsalAccessTokenProvider(instance, TEST_CONFIG);

    await expect(provider.acquireAccessToken()).resolves.toBe(TEST_TOKEN);
    expect(instance.acquireTokenSilent).toHaveBeenCalledWith({
      account,
      scopes: [...TEST_CONFIG.eciApiScopes],
    });
  });

  it("surfaces interaction required without copying MSAL error text", async () => {
    const account = { homeAccountId: "account-1" } as AccountInfo;
    const instance = createMsalStub({
      getActiveAccount: vi.fn(() => account),
      acquireTokenSilent: vi.fn(async () => {
        throw new InteractionRequiredAuthError("interaction_required", TEST_TOKEN);
      }),
    });
    const provider = new MsalAccessTokenProvider(instance, TEST_CONFIG);
    const log = vi.spyOn(console, "info").mockImplementation(() => undefined);
    const errorLog = vi.spyOn(console, "error").mockImplementation(() => undefined);

    await expect(provider.acquireAccessToken()).rejects.toBeInstanceOf(InteractionRequiredError);
    await expect(provider.acquireAccessToken()).rejects.toThrow(
      "Interactive authentication is required.",
    );
    expect(JSON.stringify(log.mock.calls)).not.toContain(TEST_TOKEN);
    expect(JSON.stringify(errorLog.mock.calls)).not.toContain(TEST_TOKEN);
  });

  it("requires interaction when no account is present", async () => {
    const provider = new MsalAccessTokenProvider(createMsalStub(), TEST_CONFIG);
    await expect(provider.acquireAccessToken()).rejects.toBeInstanceOf(InteractionRequiredError);
  });
});
