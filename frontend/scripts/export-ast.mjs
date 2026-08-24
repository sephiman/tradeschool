// SPDX-License-Identifier: AGPL-3.0-only
/**
 * The lesson-AST half of the Android bundle export, and the text diff that proves it faithful.
 *
 * It lives here, and not in Python, because the mdast lives here: the parser dialect
 * (`lib/directives.ts`), the ONE annotator that decides which words are glossary marks and lesson
 * references (`lib/glossary/annotate.ts`) and the tap point between them and the hast hints are all
 * TypeScript. Re-deriving any of that on the backend would be the second opinion this codebase
 * refuses everywhere else.
 *
 * It is NOT the entry point. `backend/scripts/export_bundle.py` is the one command; it owns the
 * content registry, writes everything else in the bundle, and drives this script with an input file
 * so that nothing here reads `content/` or knows the manifest's shape.
 *
 * The module graph is loaded through Vite's own SSR pipeline rather than a separate TS runner, so the
 * `@/` alias and the TypeScript settings are the project's, not a second configuration to keep in step.
 *
 * Usage (from `frontend/`):
 *   node scripts/export-ast.mjs --input <ast-input.json> --out <dir> [--glossary-dir <dir>]
 *                               [--diff-report <path>] [--no-verify | --verify-only]
 *
 * `--verify-only` diffs a bundle that is already on disk WITHOUT rewriting it, which is the only way
 * a deliberate mutation can be shown to be caught.
 */

import { mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { createServer } from "vite";

function parseArgs(argv) {
  const args = { emit: true, verify: true };
  for (let i = 0; i < argv.length; i++) {
    const flag = argv[i];
    if (flag === "--input") args.input = argv[++i];
    else if (flag === "--out") args.out = argv[++i];
    else if (flag === "--diff-report") args.diffReport = argv[++i];
    else if (flag === "--glossary-dir") args.glossaryDir = argv[++i];
    else if (flag === "--no-verify") args.verify = false;
    else if (flag === "--verify-only") args.emit = false;
    else throw new Error(`unknown argument ${flag}`);
  }
  for (const required of ["input", "out"]) {
    if (!args[required]) throw new Error(`--${required} is required`);
  }
  return args;
}

/** JSON the way the whole bundle is written: sorted keys, no spaces, one trailing newline. */
function canonical(value) {
  return `${JSON.stringify(value, (_key, val) =>
    val && typeof val === "object" && !Array.isArray(val)
      ? Object.fromEntries(Object.keys(val).sort().map((k) => [k, val[k]]))
      : val,
  )}\n`;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const input = JSON.parse(readFileSync(args.input, "utf8"));

  const server = await createServer({
    configFile: resolve(import.meta.dirname, "..", "vite.config.ts"),
    server: { middlewareMode: true },
    logLevel: "error",
    appType: "custom",
  });
  try {
    const ast = await server.ssrLoadModule("/src/lib/bundle/ast.ts");
    const verify = await server.ssrLoadModule("/src/lib/bundle/verify.ts");

    const census = {};
    const written = [];
    for (const locale of args.emit ? input.locales : []) {
      const dir = resolve(args.out, locale);
      // A stale file from an earlier export is a bundle that ships two versions of a lesson.
      rmSync(dir, { recursive: true, force: true });
      mkdirSync(dir, { recursive: true });
      const inputs = ast.annotationInputs(input.glossary[locale], input.modules[locale], locale);
      const perLocale = {};
      for (const lesson of input.lessons) {
        const tree = ast.lessonAst(lesson.markdown[locale], lesson.id, inputs);
        for (const [type, count] of Object.entries(ast.nodeTypeCensus(tree))) {
          perLocale[type] = (perLocale[type] ?? 0) + count;
        }
        const path = resolve(dir, `${lesson.id}.json`);
        writeFileSync(
          path,
          canonical({ ast: tree, locale, lessonId: lesson.id, lessonKey: lesson.key }),
          "utf8",
        );
        written.push(`${locale}/${lesson.id}.json`);
      }
      census[locale] = perLocale;
    }

    if (args.emit) writeFileSync(
      resolve(args.out, "index.json"),
      canonical({
        locales: input.locales,
        lessons: input.lessons.map((lesson) => ({
          id: lesson.id,
          key: lesson.key,
          moduleId: lesson.moduleId,
          files: Object.fromEntries(input.locales.map((l) => [l, `${l}/${lesson.id}.json`])),
        })),
        nodeTypeCensus: census,
        tap: ast.BUNDLE_AST_TAP,
      }),
      "utf8",
    );
    if (args.emit) console.log(`ast: ${written.length} lesson files (${input.locales.join(", ")}) -> ${args.out}`);

    if (!args.verify) return 0;

    // The diff reads what was WRITTEN, not what was built: serialization damage is the failure mode
    // this exists to catch, and comparing the in-memory tree against itself would not see it.
    const report = { locales: {}, clean: true };
    for (const locale of input.locales) {
      const bundleText = [];
      for (const file of readdirSync(resolve(args.out, locale)).sort()) {
        const doc = JSON.parse(readFileSync(resolve(args.out, locale, file), "utf8"));
        bundleText.push(...verify.blockTexts(doc.ast));
      }
      const referenceText = input.lessons.flatMap((lesson) =>
        verify.blockTexts(ast.bareAst(lesson.exportMarkdown[locale])),
      );
      const prose = verify.diff(bundleText, referenceText);

      const glossaryPath = resolve(args.glossaryDir ?? args.out, `glossary.${locale}.json`);
      const glossary = verify.diff(
        verify.glossaryTexts(JSON.parse(readFileSync(glossaryPath, "utf8")).entries),
        verify.glossaryTexts(input.glossary[locale]),
      );
      report.locales[locale] = { prose, glossary };
      if (!verify.isClean(prose) || !verify.isClean(glossary)) report.clean = false;
      const shape = (name, result) =>
        `  ${locale} ${name.padEnd(8)} ${result.bundleTokens} bundle vs ${result.referenceTokens} web tokens · ` +
        `${Object.keys(result.delta).length} differing`;
      console.log(shape("prose", prose));
      console.log(shape("glossary", glossary));
      for (const [token, gap] of Object.entries(prose.delta).slice(0, 12)) {
        console.log(`      prose    ${gap > 0 ? "+" : ""}${gap} ${JSON.stringify(token)}`);
      }
      for (const [token, gap] of Object.entries(glossary.delta).slice(0, 12)) {
        console.log(`      glossary ${gap > 0 ? "+" : ""}${gap} ${JSON.stringify(token)}`);
      }
    }
    if (args.diffReport) writeFileSync(args.diffReport, canonical(report), "utf8");
    if (!report.clean) {
      console.error("MULTISET TEXT DIFF IS NOT EMPTY — the bundle does not carry the web's text");
      return 3;
    }
    console.log("multiset text diff: 0 (prose + glossary, both locales)");
    return 0;
  } finally {
    await server.close();
  }
}

process.exitCode = await main();
