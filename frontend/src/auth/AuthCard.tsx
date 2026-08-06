import { type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { LanguageControl, ThemeControl, ThemeCycleButton } from "@/components/layout/controls";
import { Card } from "@/components/ui/primitives";

/** Centered card used by the login and register screens. Above the card is only the logo + tagline;
 * language/theme preferences live in the card footer (below the sign-in/up link), muted. */
export function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <div className="text-2xl font-bold text-primary">{t("app.name")}</div>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{t("app.tagline")}</p>
        </div>
        <Card className="p-6">
          <h1 className="mb-4 text-lg font-semibold">{title}</h1>
          {children}
          {/* Preferences, not the task: muted, one compact row, below the sign-in/up link. */}
          <div className="mt-6 flex items-center justify-center gap-2 border-t border-border pt-4 opacity-90 dark:border-gray-800 oled:border-oled-line">
            <LanguageControl />
            {/* Full three-option control on wider screens; icon-cycle on phones so the row stays one line. */}
            <div className="hidden sm:block">
              <ThemeControl />
            </div>
            <div className="sm:hidden">
              <ThemeCycleButton />
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
