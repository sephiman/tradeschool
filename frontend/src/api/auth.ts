import { apiClient } from "@/api/client";

export type Locale = "en" | "es";

export interface Me {
  id: string;
  username: string;
  locale: Locale;
}

export async function getMe(): Promise<Me> {
  const { data } = await apiClient.get<Me>("/auth/me");
  return data;
}

export async function login(username: string, password: string): Promise<Me> {
  const { data } = await apiClient.post<Me>("/auth/login", { username, password });
  return data;
}

export async function register(username: string, password: string, locale: Locale): Promise<Me> {
  const { data } = await apiClient.post<Me>("/auth/register", { username, password, locale });
  return data;
}

export async function logout(): Promise<void> {
  await apiClient.post("/auth/logout");
}

export async function updateLocale(locale: Locale): Promise<Me> {
  const { data } = await apiClient.patch<Me>("/auth/me", { locale });
  return data;
}
