import { type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { LanguageSwitcher, ThemeSwitcher } from "@/components/layout/Switchers";
import { Card } from "@/components/ui/primitives";

/** Centered card used by the login and register screens. */
export function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 py-10">
      <div className="mb-4 flex w-full max-w-sm items-center justify-end gap-2">
        <LanguageSwitcher />
        <ThemeSwitcher />
      </div>
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <div className="text-2xl font-bold text-primary">{t("app.name")}</div>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{t("app.tagline")}</p>
        </div>
        <Card className="p-6">
          <h1 className="mb-4 text-lg font-semibold">{title}</h1>
          {children}
        </Card>
      </div>
    </div>
  );
}
