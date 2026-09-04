import { useMemo, type ReactNode } from "react";
import { ReferenceRenderingProvider } from "@/lib/markdown";
import { ReferenceLink } from "@/features/references/ReferenceLink";
import type { RefRegistry } from "@/lib/refs/registry";

/**
 * Makes every `Prose` below this point mark its module and lesson mentions.
 *
 * It exists to invert one dependency: `lib/markdown` needs to DRAW a reference and must not import a
 * component out of `features/`, so the drawing is handed down instead. Wrapping a surface is the
 * whole opt-in — the six prose call sites (a prompt, an option, an explanation, an exam question)
 * need no prop of their own.
 */
export function ReferenceProvider({
  registry,
  children,
}: {
  registry: RefRegistry | null;
  children: ReactNode;
}) {
  const value = useMemo(
    () =>
      registry
        ? {
            registry,
            render: (
              target: Parameters<typeof ReferenceLink>[0]["target"],
              node: ReactNode,
            ) => <ReferenceLink target={target}>{node}</ReferenceLink>,
          }
        : null,
    [registry],
  );
  if (!value) return <>{children}</>;
  return (
    <ReferenceRenderingProvider value={value}>
      {children}
    </ReferenceRenderingProvider>
  );
}
