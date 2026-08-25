import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { EciApiClient } from "./api/client";
import { App } from "./App";
import { MsalAuthProvider } from "./auth/MsalAuthProvider";
import { createMsalInstance, initializeMsal } from "./auth/msal";
import { MsalAccessTokenProvider } from "./auth/tokenProvider";
import { FrontendConfigError, loadFrontendConfig } from "./config/env";
import "./index.css";

function renderMessage(message: string): void {
  const root = document.getElementById("root");
  if (!root) {
    return;
  }
  createRoot(root).render(
    <main className="mx-auto max-w-lg px-6 py-16">
      <h1 className="text-2xl font-semibold text-slate-900">ECI Platform</h1>
      <p role="alert" className="mt-4 text-sm text-red-700">
        {message}
      </p>
    </main>,
  );
}

function start(): void {
  let config;
  try {
    config = loadFrontendConfig(import.meta.env);
  } catch (error) {
    const message =
      error instanceof FrontendConfigError
        ? error.message
        : "Frontend configuration is missing or invalid.";
    renderMessage(message);
    return;
  }

  const msalInstance = createMsalInstance(config);
  const apiClient = new EciApiClient({
    baseUrl: config.apiBaseUrl,
    tokenProvider: new MsalAccessTokenProvider(msalInstance, config),
  });

  void initializeMsal(msalInstance)
    .then(() => {
      const root = document.getElementById("root");
      if (!root) {
        return;
      }
      createRoot(root).render(
        <StrictMode>
          <MsalAuthProvider config={config} instance={msalInstance}>
            <App apiClient={apiClient} />
          </MsalAuthProvider>
        </StrictMode>,
      );
    })
    .catch(() => {
      renderMessage("Authentication could not be initialized.");
    });
}

start();
