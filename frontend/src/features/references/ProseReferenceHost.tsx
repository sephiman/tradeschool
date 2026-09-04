import { useMemo, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { getCourse } from "@/api/course";
import { TermPopoverHost } from "@/features/glossary/TermPopover";
import { ReferenceProvider } from "@/features/references/ReferenceProvider";
import { buildRefRegistry, refModulesFromCourse } from "@/lib/refs/registry";

/**
 * Reference marks and the panel that shows them, for a surface that is all prose and no glossary.
 *
 * The exam pages read exercise prose without any of a lesson page's machinery, so this is the one
 * line that gives them the same affordance: the popover host the panel needs, and a registry built
 * from the course the reader already fetched — same query key as everywhere else, so a warm cache
 * costs nothing and a cold one costs the fetch the page would need anyway to name its own blocks.
 */

/** Stable identity: a fresh `Map` each render would remount the host's context on every keystroke. */
const NO_GLOSSARY = new Map();

export function ProseReferenceHost({ children }: { children: ReactNode }) {
  const { i18n } = useTranslation();
  const { data: course } = useQuery({
    queryKey: ["course", i18n.resolvedLanguage],
    queryFn: getCourse,
  });
  const registry = useMemo(
    () => (course ? buildRefRegistry(refModulesFromCourse(course)) : null),
    [course],
  );
  return (
    <TermPopoverHost entries={NO_GLOSSARY}>
      <ReferenceProvider registry={registry}>{children}</ReferenceProvider>
    </TermPopoverHost>
  );
}
