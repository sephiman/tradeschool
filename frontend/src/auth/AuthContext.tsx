import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import * as authApi from "@/api/auth";
import type { Locale, Me } from "@/api/auth";

interface AuthContextValue {
  user: Me | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string, locale: Locale) => Promise<void>;
  logout: () => Promise<void>;
  setLocale: (locale: Locale) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const { i18n } = useTranslation();
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const applyUserLocale = useCallback(
    (me: Me) => {
      if (me.locale && me.locale !== i18n.resolvedLanguage) void i18n.changeLanguage(me.locale);
    },
    [i18n],
  );

  useEffect(() => {
    void (async () => {
      try {
        const me = await authApi.getMe();
        setUser(me);
        applyUserLocale(me);
      } catch {
        setUser(null);
      } finally {
        setLoading(false);
      }
    })();
    // Run once on mount; applyUserLocale is stable enough for this bootstrap.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(
    async (username: string, password: string) => {
      const me = await authApi.login(username, password);
      setUser(me);
      applyUserLocale(me);
    },
    [applyUserLocale],
  );

  const register = useCallback(
    async (username: string, password: string, locale: Locale) => {
      await authApi.register(username, password, locale);
      const me = await authApi.login(username, password);
      setUser(me);
      applyUserLocale(me);
    },
    [applyUserLocale],
  );

  const logout = useCallback(async () => {
    await authApi.logout();
    setUser(null);
  }, []);

  const setLocale = useCallback(
    async (locale: Locale) => {
      void i18n.changeLanguage(locale);
      if (user) {
        const me = await authApi.updateLocale(locale);
        setUser(me);
      }
    },
    [i18n, user],
  );

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, login, register, logout, setLocale }),
    [user, loading, login, register, logout, setLocale],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
