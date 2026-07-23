import { apiClient } from "@/api/client";

export type Locale = "en" | "es";

export interface Me {
  id: string;
  email: string;
  locale: Locale;
}

export async function getMe(): Promise<Me> {
  const { data } = await apiClient.get<Me>("/auth/me");
  return data;
}

export async function login(email: string, password: string): Promise<Me> {
  const { data } = await apiClient.post<Me>("/auth/login", { email, password });
  return data;
}

export async function register(email: string, password: string, locale: Locale): Promise<Me> {
  const { data } = await apiClient.post<Me>("/auth/register", { email, password, locale });
  return data;
}

export async function logout(): Promise<void> {
  await apiClient.post("/auth/logout");
}

export async function updateLocale(locale: Locale): Promise<Me> {
  const { data } = await apiClient.patch<Me>("/auth/me", { locale });
  return data;
}
