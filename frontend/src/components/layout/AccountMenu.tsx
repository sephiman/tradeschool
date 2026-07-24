import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Me } from "@/api/auth";
import { useAuth } from "@/auth/AuthContext";
import { LanguageControl, ThemeControl } from "@/components/layout/controls";

function initials(username: string): string {
  return username.slice(0, 2).toUpperCase();
}

/** Account controls collapsed behind an avatar button (SharedLedger pattern): signed-in-as,
 * segmented language + theme, and sign out. Used at every width so the header never overflows. */
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
        className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1 dark:focus:ring-offset-gray-900"
      >
        {initials(user.username)}
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-2 w-64 max-w-[calc(100vw-2rem)] space-y-3 rounded-lg border border-border bg-white p-3 shadow-lg dark:border-gray-800 dark:bg-gray-900"
        >
          <div className="px-1">
            <p className="text-xs text-gray-500 dark:text-gray-400">{t("auth.signedInAs")}</p>
            <p className="truncate font-semibold">{user.username}</p>
          </div>

          <div className="border-t border-border pt-3 dark:border-gray-800">
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
            className="w-full rounded-md border border-border px-3 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-100 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800"
          >
            {t("auth.logout")}
          </button>
        </div>
      )}
    </div>
  );
}
