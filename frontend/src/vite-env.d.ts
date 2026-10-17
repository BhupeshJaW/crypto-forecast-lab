/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "" (same origin via the dev proxy) or an absolute http(s) URL. Never put secrets in VITE_* variables. */
  readonly VITE_API_BASE_URL?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
