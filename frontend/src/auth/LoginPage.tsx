import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { apiErrorMessage } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { AuthCard } from "@/auth/AuthCard";
import { Button, Input, Label } from "@/components/ui/primitives";

export function LoginPage() {
  const { t } = useTranslation();
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const next = new URLSearchParams(location.search).get("next") ?? "/";

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={next} replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(username, password);
      navigate(next, { replace: true });
    } catch (err) {
      setError(apiErrorMessage(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard title={t("auth.loginTitle")}>
      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <Label htmlFor="username">{t("auth.username")}</Label>
          <Input id="username" type="text" autoComplete="username" autoCapitalize="none" spellCheck={false} required value={username} onChange={(e) => setUsername(e.target.value)} />
        </div>
        <div>
          <Label htmlFor="password">{t("auth.password")}</Label>
          <Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        <Button type="submit" disabled={busy} className="w-full">
          {busy ? t("common.loading") : t("auth.loginAction")}
        </Button>
      </form>
      <p className="mt-4 text-center text-sm text-gray-500 dark:text-gray-400">
        {t("auth.noAccount")}{" "}
        <Link to="/register" className="font-medium text-primary hover:underline">
          {t("auth.registerAction")}
        </Link>
      </p>
    </AuthCard>
  );
}
