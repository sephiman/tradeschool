import { type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/ui/primitives";
import { LanguageSwitcher, ThemeSwitcher } from "@/components/layout/Switchers";
import { cn } from "@/lib/cn";

export function AppShell({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const { user, logout } = useAuth();

  return (
    <div className="flex min-h-full flex-col">
      <header className="border-b border-border bg-white dark:border-gray-800 dark:bg-gray-900">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-6">
            <span className="text-lg font-semibold text-primary">{t("app.name")}</span>
            {user && (
              <nav className="flex items-center gap-4 text-sm">
                {(
                  [
                    ["/course", t("nav.course")],
                    ["/stats", t("nav.progress")],
                  ] as const
                ).map(([to, label]) => (
                  <NavLink
                    key={to}
                    to={to}
                    className={({ isActive }) =>
                      cn(
                        "hover:text-primary",
                        isActive ? "font-medium text-primary" : "text-gray-600 dark:text-gray-300",
                      )
                    }
                  >
                    {label}
                  </NavLink>
                ))}
              </nav>
            )}
          </div>
          <div className="flex items-center gap-3">
            <LanguageSwitcher />
            <ThemeSwitcher />
            {user && (
              <>
                <span className="hidden max-w-[12rem] truncate text-sm text-gray-500 sm:inline dark:text-gray-400">
                  {user.email}
                </span>
                <Button variant="ghost" onClick={() => void logout()}>
                  {t("auth.logout")}
                </Button>
              </>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">{children}</main>
    </div>
  );
}
