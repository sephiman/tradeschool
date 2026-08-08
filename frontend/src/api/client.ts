import axios, { type AxiosError } from "axios";
import i18n from "@/i18n";

// Cookie auth uses fastapi-users cookie transport with SameSite=Lax, which blocks cross-site
// state-changing requests at the browser — so no XSRF double-submit token is needed. We only
// need cookies to travel with same-origin requests.
export const apiClient = axios.create({
  baseURL: "/api",
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
});

// Serve every request in the active UI language: the backend's content endpoints resolve locale from
// `?lang`. Without this the content followed the user's registration locale and ignored the switcher.
// Explicit per-call `lang` params still win. (React-query keys also include the locale, so a switch
// refetches rather than showing stale cache.)
apiClient.interceptors.request.use((config) => {
  const lang = i18n.resolvedLanguage?.startsWith("es") ? "es" : "en";
  config.params = { lang, ...(config.params ?? {}) };
  return config;
});

export interface ApiError {
  code: string;
  message: string;
  fields?: Record<string, string>;
}

export function asApiError(err: unknown): ApiError {
  const ax = err as AxiosError<ApiError>;
  if (ax?.response?.data?.code) return ax.response.data;
  return { code: "UNKNOWN", message: ax?.message ?? "Unknown error" };
}

/** Localized message for a failed request: the `errors.<code>` translation, falling back to the server message. */
export function apiErrorMessage(err: unknown, t: (key: string, fallback: string) => string): string {
  const api = asApiError(err);
  return t(`errors.${api.code}`, api.message);
}

/**
 * The course every course-owned URL hangs off.
 *
 * One course exists today, and its slug is a permanent identifier (see content/README.md) — the same
 * id the manifest and the PDF filename already use. The unscoped URLs still work as deprecated
 * aliases for clients we do not control; ours never use them.
 */
export const COURSE_SLUG = "crypto-futures";
export const COURSE_PATH = `/courses/${COURSE_SLUG}`;
