/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ECI_API_BASE_URL?: string;
  readonly VITE_ENTRA_AUTHORITY?: string;
  readonly VITE_ENTRA_SPA_CLIENT_ID?: string;
  readonly VITE_ENTRA_REDIRECT_URI?: string;
  readonly VITE_ECI_API_SCOPES?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
