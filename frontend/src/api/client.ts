import axios, { type AxiosError } from "axios";

// Cookie auth uses fastapi-users cookie transport with SameSite=Lax, which blocks cross-site
// state-changing requests at the browser — so no XSRF double-submit token is needed. We only
// need cookies to travel with same-origin requests.
export const apiClient = axios.create({
  baseURL: "/api",
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
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
