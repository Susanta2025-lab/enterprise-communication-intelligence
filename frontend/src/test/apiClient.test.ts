import { describe, expect, it, vi } from "vitest";

import { EciApiClient } from "../api/client";
import {
  CONNECTOR_ACCOUNTS_PATH,
  EciApiError,
  GMAIL_AUTHORIZE_PATH,
  MICROSOFT_GRAPH_AUTHORIZE_PATH,
  PROTECTED_ANALYSES_SMOKE_PATH,
} from "../api/errors";
import { InteractionRequiredError } from "../auth/tokenProvider";
import { TEST_TOKEN } from "./fixtures";

const REQUEST_ID = "11111111-1111-4111-8111-111111111111";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("ECI API client", () => {
  it("attaches a bearer token and request id for the analyses smoke contract", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => jsonResponse(200, { items: [], limit: 1, offset: 0 }));
    const client = new EciApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: { acquireAccessToken: async () => TEST_TOKEN },
      fetchImpl,
      createRequestId: () => REQUEST_ID,
    });
    const log = vi.spyOn(console, "info").mockImplementation(() => undefined);

    await expect(client.getAnalysesSmoke()).resolves.toEqual({
      items: [],
      limit: 1,
      offset: 0,
    });

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(fetchImpl).toHaveBeenCalledWith(
      expect.stringContaining(PROTECTED_ANALYSES_SMOKE_PATH),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: `Bearer ${TEST_TOKEN}`,
          "X-Request-ID": REQUEST_ID,
        }),
      }),
    );
    expect(JSON.stringify(log.mock.calls)).not.toContain(TEST_TOKEN);
  });

  it("lists owned connector accounts with a bearer token", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () =>
      jsonResponse(200, { items: [], limit: 20, offset: 0 }),
    );
    const client = new EciApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: { acquireAccessToken: async () => TEST_TOKEN },
      fetchImpl,
      createRequestId: () => REQUEST_ID,
    });
    await expect(client.listConnectorAccounts()).resolves.toEqual({
      items: [],
      limit: 20,
      offset: 0,
    });
    expect(fetchImpl).toHaveBeenCalledWith(
      expect.stringContaining(`${CONNECTOR_ACCOUNTS_PATH}?limit=20&offset=0`),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: `Bearer ${TEST_TOKEN}`,
          "X-Request-ID": REQUEST_ID,
        }),
      }),
    );
  });

  it("starts Gmail and Microsoft authorization without logging URLs", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes(GMAIL_AUTHORIZE_PATH)) {
        return jsonResponse(200, {
          authorization_url: "https://accounts.google.com/o/oauth2/v2/auth",
          expires_at: "2026-08-25T00:00:00Z",
        });
      }
      return jsonResponse(200, {
        authorization_url: "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize",
        expires_at: "2026-08-25T00:00:00Z",
      });
    });
    const log = vi.spyOn(console, "info").mockImplementation(() => undefined);
    const client = new EciApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: { acquireAccessToken: async () => TEST_TOKEN },
      fetchImpl,
    });
    await client.startGmailAuthorization();
    await client.startMicrosoftGraphAuthorization();
    expect(fetchImpl.mock.calls[0]?.[0]).toEqual(expect.stringContaining(GMAIL_AUTHORIZE_PATH));
    expect(fetchImpl.mock.calls[1]?.[0]).toEqual(
      expect.stringContaining(MICROSOFT_GRAPH_AUTHORIZE_PATH),
    );
    expect(JSON.stringify(log.mock.calls)).not.toContain("accounts.google.com");
    log.mockRestore();
  });

  it.each([
    [401, "unauthorized"],
    [403, "forbidden"],
    [404, "not_found"],
    [409, "conflict"],
    [422, "validation"],
    [503, "unavailable"],
  ] as const)("normalizes HTTP %s", async (status, kind) => {
    const fetchImpl = vi.fn<typeof fetch>(async () => jsonResponse(status, { detail: TEST_TOKEN }));
    const client = new EciApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: { acquireAccessToken: async () => TEST_TOKEN },
      fetchImpl,
    });

    try {
      await client.getAnalysesSmoke();
      throw new Error("expected EciApiError");
    } catch (error) {
      expect(error).toBeInstanceOf(EciApiError);
      const apiError = error as EciApiError;
      expect(apiError.status).toBe(status);
      expect(apiError.kind).toBe(kind);
      expect(apiError.message).not.toContain(TEST_TOKEN);
    }
  });

  it("does not call fetch when interactive authentication is required", async () => {
    const fetchImpl = vi.fn<typeof fetch>();
    const client = new EciApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: {
        acquireAccessToken: async () => {
          throw new InteractionRequiredError();
        },
      },
      fetchImpl,
    });

    await expect(client.getAnalysesSmoke()).rejects.toMatchObject({
      kind: "interaction_required",
    });
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});
