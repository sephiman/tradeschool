import { useEffect, useRef, useState } from "react";
import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { Me } from "@/api/auth";
import { useAuth } from "@/auth/AuthContext";
import { LanguageControl, ThemeControl } from "@/components/layout/controls";
import { NAV_ITEMS } from "@/components/layout/nav";
import { cn } from "@/lib/cn";

function initials(username: string): string {
  return username.slice(0, 2).toUpperCase();
}

/** Account controls collapsed behind an avatar button (SharedLedger pattern): signed-in-as,
 * segmented language + theme, and sign out. Below `sm` the primary nav folds in here as a top
 * section too (one single menu), so the header never has to fit the links. */
export function AccountMenu({ user }: { user: Me }) {
  const { t } = useTranslation();
  const { logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={user.username}
        onClick={() => setOpen((v) => !v)}
        className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1 dark:focus:ring-offset-gray-900 oled:focus:ring-offset-oled-bg"
      >
        {initials(user.username)}
      </button>

      {/* The one floating panel in the app, and the case the OLED brief calls a modal: it is told
          apart from the page underneath by `shadow-lg` and a lighter fill, neither of which survives
          #000-on-#000. It gets the strong border — a menu overlapping content has to read as being
          *in front of* it, which a hairline seam does not do. */}
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-2 w-64 max-w-[calc(100vw-2rem)] rounded-lg border border-border bg-white p-3 shadow-lg dark:border-gray-800 dark:bg-gray-900 oled:border-oled-line-strong oled:bg-oled-bg"
        >
          {/* Primary nav, only when it was collapsed out of the header (< sm). Active page keeps its
              highlight here. Same single menu on mobile — nav, divider, then account controls. */}
          <nav className="mb-3 flex flex-col border-b border-border pb-3 sm:hidden dark:border-gray-800 oled:border-oled-line">
            {NAV_ITEMS.map(({ to, labelKey }) => (
              <NavLink
                key={to}
                to={to}
                onClick={() => setOpen(false)}
                className={({ isActive }) =>
                  cn(
                    "rounded-md px-2 py-1.5 text-sm transition-colors",
                    isActive
                      ? "bg-primary/10 font-medium text-primary"
                      : "text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-gray-800 oled:hover:bg-oled-hover",
                  )
                }
              >
                {t(labelKey)}
              </NavLink>
            ))}
          </nav>

          <div className="space-y-3">
            <div className="px-1">
              <p className="text-xs text-gray-500 dark:text-gray-400">{t("auth.signedInAs")}</p>
              <p className="truncate font-semibold">{user.username}</p>
            </div>

            <div className="border-t border-border pt-3 dark:border-gray-800 oled:border-oled-line">
              <p className="mb-1 px-1 text-xs text-gray-500 dark:text-gray-400">{t("common.language")}</p>
              <LanguageControl block />
            </div>

            <div>
              <p className="mb-1 px-1 text-xs text-gray-500 dark:text-gray-400">{t("common.theme")}</p>
              <ThemeControl block />
            </div>

            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                void logout();
              }}
              className="w-full rounded-md border border-border px-3 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-100 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800 oled:border-oled-line-strong oled:hover:bg-oled-hover"
            >
              {t("auth.logout")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
