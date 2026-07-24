import { type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/auth/AuthContext";
import { AccountMenu } from "@/components/layout/AccountMenu";
import { NAV_ITEMS } from "@/components/layout/nav";
import { cn } from "@/lib/cn";

export function AppShell({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const { user } = useAuth();

  return (
    <div className="flex min-h-full flex-col">
      <header className="border-b border-border bg-white dark:border-gray-800 dark:bg-gray-900">
        {/* Logo and avatar never shrink or clip; the nav between them collapses into the avatar menu
            below `sm`, where it would otherwise crowd them (space-driven — a narrowed window too). */}
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3">
          <div className="flex min-w-0 items-center gap-6">
            <span className="shrink-0 text-lg font-semibold text-primary">{t("app.name")}</span>
            {user && (
              <nav className="hidden items-center gap-4 text-sm sm:flex">
                {NAV_ITEMS.map(({ to, labelKey }) => (
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
                    {t(labelKey)}
                  </NavLink>
                ))}
              </nav>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-3">{user && <AccountMenu user={user} />}</div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">{children}</main>
    </div>
  );
}
