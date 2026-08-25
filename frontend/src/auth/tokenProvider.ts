import {
  InteractionRequiredAuthError,
  type AccountInfo,
  type IPublicClientApplication,
} from "@azure/msal-browser";

import type { FrontendConfig } from "../config/env";

export class InteractionRequiredError extends Error {
  readonly name = "InteractionRequiredError";

  constructor() {
    super("Interactive authentication is required.");
  }
}

export type AccessTokenProvider = {
  acquireAccessToken: () => Promise<string>;
};

export class MsalAccessTokenProvider implements AccessTokenProvider {
  private readonly instance: IPublicClientApplication;
  private readonly config: FrontendConfig;

  constructor(instance: IPublicClientApplication, config: FrontendConfig) {
    this.instance = instance;
    this.config = config;
  }

  async acquireAccessToken(): Promise<string> {
    const account = this.resolveAccount();
    if (account === null) {
      throw new InteractionRequiredError();
    }

    try {
      const result = await this.instance.acquireTokenSilent({
        account,
        scopes: [...this.config.eciApiScopes],
      });
      if (!result.accessToken) {
        throw new InteractionRequiredError();
      }
      return result.accessToken;
    } catch (error) {
      if (
        error instanceof InteractionRequiredAuthError ||
        error instanceof InteractionRequiredError
      ) {
        throw new InteractionRequiredError();
      }
      throw error;
    }
  }

  private resolveAccount(): AccountInfo | null {
    return this.instance.getActiveAccount() ?? this.instance.getAllAccounts()[0] ?? null;
  }
}
