import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { Locale } from "@/api/auth";
import { apiErrorMessage } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { AuthCard } from "@/auth/AuthCard";
import { Button, Input, Label } from "@/components/ui/primitives";

const MIN_PASSWORD = 8;
const USERNAME_RE = /^[a-z0-9_-]{3,32}$/;

export function RegisterPage() {
  const { t, i18n } = useTranslation();
  const { user, register } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const uname = username.trim().toLowerCase();
    if (!USERNAME_RE.test(uname)) {
      setError(t("auth.usernameInvalid"));
      return;
    }
    if (password.length < MIN_PASSWORD) {
      setError(t("auth.passwordTooShort", { count: MIN_PASSWORD }));
      return;
    }
    setBusy(true);
    try {
      const locale = (i18n.resolvedLanguage === "es" ? "es" : "en") as Locale;
      await register(uname, password, locale);
      navigate("/", { replace: true });
    } catch (err) {
      setError(apiErrorMessage(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard title={t("auth.registerTitle")}>
      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <Label htmlFor="username">{t("auth.username")}</Label>
          <Input id="username" type="text" autoComplete="username" autoCapitalize="none" spellCheck={false} required minLength={3} maxLength={32} value={username} onChange={(e) => setUsername(e.target.value)} />
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{t("auth.usernameHint")}</p>
        </div>
        <div>
          <Label htmlFor="password">{t("auth.password")}</Label>
          <Input id="password" type="password" autoComplete="new-password" required minLength={MIN_PASSWORD} value={password} onChange={(e) => setPassword(e.target.value)} />
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{t("auth.passwordHint", { count: MIN_PASSWORD })}</p>
        </div>
        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        <Button type="submit" disabled={busy} className="w-full">
          {busy ? t("common.loading") : t("auth.registerAction")}
        </Button>
      </form>
      <p className="mt-4 text-center text-sm text-gray-500 dark:text-gray-400">
        {t("auth.haveAccount")}{" "}
        <Link to="/login" className="font-medium text-primary hover:underline">
          {t("auth.loginAction")}
        </Link>
      </p>
    </AuthCard>
  );
}
