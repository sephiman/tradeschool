import { type ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/auth/AuthContext";
import { AccountMenu } from "@/components/layout/AccountMenu";
import { HOME_PATH, NAV_ITEMS } from "@/components/layout/nav";
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
            {/* The wordmark is the way back to the start from anywhere. A plain `Link`, deliberately
                with no `replace` prop: react-router replaces only when the target already IS the
                current location, so clicking it on the course page adds no history entry while
                clicking it on a lesson leaves that lesson for Back to return to. The accessible name
                keeps the visible text inside it ("TradeSchool — home"), which is what lets someone
                driving by voice say what they can read. */}
            <Link
              to={HOME_PATH}
              aria-label={t("nav.homeLabel", { name: t("app.name") })}
              className="shrink-0 rounded-md text-lg font-semibold text-primary transition-opacity hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1 dark:focus:ring-offset-gray-900"
            >
              {t("app.name")}
            </Link>
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
