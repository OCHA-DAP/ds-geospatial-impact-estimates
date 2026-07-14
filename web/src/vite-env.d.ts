/// <reference types="vite/client" />

// Deploy-target env vars (see src/config.ts). Optional: unset = classic same-origin build.
interface ImportMetaEnv {
  readonly VITE_TOKEN_URL?: string;
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
