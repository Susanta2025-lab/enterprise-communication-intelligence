import type { AccessTokenProvider } from "../auth/tokenProvider";
import { InteractionRequiredError } from "../auth/tokenProvider";
import {
  EciApiError,
  kindForStatus,
  messageForKind,
  PROTECTED_ANALYSES_SMOKE_PATH,
  type AnalysisListResponse,
} from "./errors";

type FetchLike = typeof fetch;

export type EciApiClientOptions = {
  baseUrl: string;
  tokenProvider: AccessTokenProvider;
  fetchImpl?: FetchLike;
  createRequestId?: () => string;
};

export class EciApiClient {
  private readonly baseUrl: string;
  private readonly tokenProvider: AccessTokenProvider;
  private readonly fetchImpl: FetchLike;
  private readonly createRequestId: () => string;

  constructor(options: EciApiClientOptions) {
    this.baseUrl = options.baseUrl;
    this.tokenProvider = options.tokenProvider;
    this.fetchImpl = options.fetchImpl ?? fetch.bind(globalThis);
    this.createRequestId = options.createRequestId ?? (() => crypto.randomUUID());
  }

  async getAnalysesSmoke(): Promise<AnalysisListResponse> {
    return this.requestJson<AnalysisListResponse>("GET", PROTECTED_ANALYSES_SMOKE_PATH);
  }

  private async requestJson<T>(method: string, path: string, body?: unknown): Promise<T> {
    let token: string;
    try {
      token = await this.tokenProvider.acquireAccessToken();
    } catch (error) {
      if (error instanceof InteractionRequiredError) {
        throw new EciApiError(401, "interaction_required", messageForKind("interaction_required"));
      }
      throw error;
    }

    const headers: Record<string, string> = {
      Accept: "application/json",
      Authorization: `Bearer ${token}`,
      "X-Request-ID": this.createRequestId(),
    };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
    }

    const response = await this.fetchImpl(new URL(path, `${this.baseUrl}/`).toString(), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });

    if (!response.ok) {
      const kind = kindForStatus(response.status);
      throw new EciApiError(response.status, kind, messageForKind(kind));
    }

    return (await response.json()) as T;
  }
}
