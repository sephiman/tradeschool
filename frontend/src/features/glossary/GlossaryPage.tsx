import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { getGlossary, type GlossaryEntry } from "@/api/course";
import { sortGlossary } from "@/lib/glossary";
import { Card, Input, Spinner } from "@/components/ui/primitives";
import { coursePath } from "@/components/layout/nav";

/**
 * The glossary: every term the course defines, alphabetical in the reader's locale.
 *
 * Ordering comes from `sortGlossary`, the same function the PDF uses, so the page and the book list
 * the terms identically. Aliases render as pointers into the canonical entry rather than repeating
 * a definition, and every origin is a link into the lesson that teaches the term.
 */

/** Fold case and accents so searching "emision" finds `emisión`. */
function fold(value: string): string {
  return value
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

function matches(entry: GlossaryEntry, needle: string): boolean {
  if (!needle) return true;
  const haystack = [
    entry.term,
    entry.definition ?? "",
    entry.aliasOf?.term ?? "",
    ...(entry.senses ?? []).map((s) => s.definition),
  ].join(" ");
  return fold(haystack).includes(fold(needle));
}

function OriginLink({ origin, title }: { origin: string | null; title: string | null }) {
  const { t } = useTranslation();
  if (!origin) return null;
  return (
    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
      {t("glossary.originLabel")}{" "}
      <Link to={coursePath(`/lessons/${origin}`)} className="text-primary hover:underline">
        <span className="tabular-nums">{origin.toUpperCase()}</span>
        {title ? ` · ${title}` : ""}
      </Link>
    </p>
  );
}

function Entry({ entry }: { entry: GlossaryEntry }) {
  const { t } = useTranslation();
  return (
    <Card id={entry.id} className="scroll-mt-24 p-4">
      <h2 className="font-semibold">{entry.term}</h2>

      {entry.aliasOf ? (
        // A pointer, not a second copy of the definition: the canonical entry owns the words.
        <p className="mt-1 text-sm">
          <span className="text-gray-500 dark:text-gray-400">{t("glossary.aliasHint")}</span>{" "}
          <a href={`#${entry.aliasOf.id}`} className="text-primary hover:underline">
            {entry.aliasOf.term}
          </a>
        </p>
      ) : (
        entry.definition && (
          <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">{entry.definition}</p>
        )
      )}

      {(entry.senses ?? []).map((sense, index) => (
        <div key={sense.origin + index} className="mt-2 border-l-2 border-gray-200 pl-3 dark:border-gray-700">
          <p className="text-sm text-gray-700 dark:text-gray-300">
            <span className="font-semibold text-primary">{t("glossary.sense", { index: index + 1 })}</span>
            {sense.definition}
          </p>
          <OriginLink origin={sense.origin} title={sense.originTitle} />
        </div>
      ))}

      {/* A homonym's origins are per-sense, printed above; only a single-sense entry has one here. */}
      {!entry.senses?.length && <OriginLink origin={entry.origin} title={entry.originTitle} />}
    </Card>
  );
}

export function GlossaryPage() {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  const { hash } = useLocation();
  const [query, setQuery] = useState("");

  const { data, isPending, isError } = useQuery({
    queryKey: ["glossary", locale],
    queryFn: () => getGlossary(locale),
  });

  // The server already sorts, but the page re-sorts through the shared collator so that the screen
  // and the PDF are guaranteed to agree — Intl.Collator is the single source of the order.
  const entries = useMemo(
    () => (data ? sortGlossary(data.terms, locale) : []),
    [data, locale],
  );
  const shown = useMemo(() => entries.filter((e) => matches(e, query)), [entries, query]);

  // A tooltip's "full entry" link arrives as /glossary#g-funding through the router, which — unlike
  // the in-page alias anchors — does no scrolling of its own, and on a cold load the entry does not
  // exist yet anyway. So the scroll happens here, once the entries are on the page. (`scroll-mt-24`
  // on the card is what keeps the term clear of the sticky header.)
  useEffect(() => {
    if (!hash || shown.length === 0) return;
    document.getElementById(hash.slice(1))?.scrollIntoView({ block: "start" });
  }, [hash, shown.length]);

  if (isPending) {
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    );
  }
  if (isError) return <p className="py-16 text-center text-gray-500">{t("glossary.loadFailed")}</p>;

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-bold">{t("glossary.title")}</h1>
      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{t("glossary.subtitle")}</p>

      <div className="mt-4 flex items-center gap-3">
        <Input
          type="search"
          aria-label={t("glossary.search")}
          placeholder={t("glossary.searchPlaceholder")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className="shrink-0 text-xs text-gray-500 dark:text-gray-400">
          {t("glossary.count", { count: shown.length })}
        </span>
      </div>

      {shown.length === 0 ? (
        <p className="py-12 text-center text-gray-500">{t("glossary.empty")}</p>
      ) : (
        <div className="mt-4 grid gap-3">
          {shown.map((entry) => (
            <Entry key={entry.id} entry={entry} />
          ))}
        </div>
      )}
    </div>
  );
}
