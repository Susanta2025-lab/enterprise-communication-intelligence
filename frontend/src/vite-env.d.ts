/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ECI_API_BASE_URL?: string;
  readonly VITE_ENTRA_AUTHORITY?: string;
  readonly VITE_ENTRA_SPA_CLIENT_ID?: string;
  readonly VITE_ENTRA_REDIRECT_URI?: string;
  readonly VITE_ECI_API_SCOPES?: string;
  /** Public build-time presentation metadata. Not credentials or authorization. */
  readonly VITE_ECI_CLOUD_PROVIDER?: string;
  /** Public build-time presentation metadata. Not credentials or authorization. */
  readonly VITE_ECI_AI_PROVIDER?: string;
  /** Public build-time presentation metadata. Safe display region label only. */
  readonly VITE_ECI_CLOUD_REGION?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
