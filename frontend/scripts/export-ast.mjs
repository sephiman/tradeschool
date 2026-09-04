// SPDX-License-Identifier: AGPL-3.0-only
/**
 * The lesson-AST half of the Android bundle export, and the two checks that prove it faithful.
 *
 * The multiset diff answers "are these the same words"; the block check answers "is this the same
 * page", against the HTML `LessonMarkdown` actually paints. The second exists because the first
 * splits on whitespace (so no whitespace bug can reach it), is a bag (so word order is not in it),
 * and takes its reference from the same parser the bundle uses (so a change to that parser moves
 * both sides at once). See `src/lib/bundle/verify.ts`.
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
 * `--verify-only` checks a bundle that is already on disk WITHOUT rewriting it, which is the only way
 * a deliberate mutation can be shown to be caught.
 */

import { mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { createServer } from "vite";

function parseArgs(argv) {
  const args = { emit: true, verify: true };
  for (let i = 0; i < argv.length; i++) {
    const flag = argv[i];
    if (flag === "--input") args.input = argv[++i];
    else if (flag === "--out") args.out = argv[++i];
    else if (flag === "--diff-report") args.diffReport = argv[++i];
    else if (flag === "--glossary-dir") args.glossaryDir = argv[++i];
    else if (flag === "--refs-out") args.refsOut = argv[++i];
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
    const rendered = await server.ssrLoadModule("/src/lib/bundle/rendered.tsx");
    const exerciseRefs = await server.ssrLoadModule("/src/lib/bundle/exerciseRefs.ts");

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

    if (args.emit && args.refsOut) {
      // The SAME annotator that marks a lesson's references, over the prose inside exercise configs.
      // Offsets into the string the bundle carries, so the app resolves nothing and detects nothing.
      const references = {};
      let marked = 0;
      for (const locale of input.locales) {
        const registry = ast.annotationInputs([], input.modules[locale], locale).registry;
        for (const entry of input.exerciseTexts ?? []) {
          const marks = exerciseRefs.exerciseRefs(entry.text[locale], registry);
          if (marks.length === 0) continue;
          ((references[entry.exerciseId] ??= {})[locale] ??= {})[entry.path] = marks;
          marked += marks.length;
        }
      }
      writeFileSync(
        args.refsOut,
        canonical({ kind: "exercise-references", detector: ast.BUNDLE_REF_DETECTOR, references }),
        "utf8",
      );
      console.log(
        `refs: ${marked} resolved reference(s) in ${Object.keys(references).length} exercises -> ${args.refsOut}`,
      );
    }

    if (!args.verify) return 0;

    // Both checks read what was WRITTEN, not what was built: serialization damage is a failure mode
    // they exist to catch, and comparing the in-memory tree against itself would not see it.
    const host = new JSDOM("").window.document.createElement("div");
    const report = { locales: {}, clean: true };
    for (const locale of input.locales) {
      const dir = resolve(args.out, locale);
      const bundleText = [];
      const blocks = [];
      for (const lesson of input.lessons) {
        const doc = JSON.parse(readFileSync(resolve(dir, `${lesson.id}.json`), "utf8"));
        bundleText.push(...verify.blockTexts(doc.ast));
        // The page the web paints from the SAME markdown, through `LessonMarkdown` rather than
        // through anything in `bundle/`: the one reference here that is not this pipeline's opinion.
        host.innerHTML = rendered.lessonHtml(lesson.markdown[locale]);
        const mismatches = verify.blockDiff(verify.bundleBlocks(doc.ast), verify.renderedBlocks(host));
        if (mismatches.length) blocks.push({ lessonId: lesson.id, mismatches });
      }
      // Read by lesson id above, so a file no lesson names is no longer read at all — it has to be
      // named here or a lesson left behind by an earlier export would ship unnoticed.
      const strays = readdirSync(dir).filter(
        (file) => !input.lessons.some((lesson) => `${lesson.id}.json` === file),
      );

      const referenceText = input.lessons.flatMap((lesson) =>
        verify.blockTexts(ast.bareAst(lesson.exportMarkdown[locale])),
      );
      const prose = verify.diff(bundleText, referenceText);

      const glossaryPath = resolve(args.glossaryDir ?? args.out, `glossary.${locale}.json`);
      const glossary = verify.diff(
        verify.glossaryTexts(JSON.parse(readFileSync(glossaryPath, "utf8")).entries),
        verify.glossaryTexts(input.glossary[locale]),
      );
      report.locales[locale] = { prose, glossary, blocks, strays };
      if (!verify.isClean(prose) || !verify.isClean(glossary)) report.clean = false;
      if (blocks.length || strays.length) report.clean = false;
      const shape = (name, result) =>
        `  ${locale} ${name.padEnd(8)} ${result.bundleTokens} bundle vs ${result.referenceTokens} web tokens · ` +
        `${Object.keys(result.delta).length} differing`;
      console.log(shape("prose", prose));
      console.log(shape("glossary", glossary));
      console.log(
        `  ${locale} ${"blocks".padEnd(8)} ${input.lessons.length} lessons vs the rendered page · ` +
        `${blocks.length} disagreeing`,
      );
      for (const [token, gap] of Object.entries(prose.delta).slice(0, 12)) {
        console.log(`      prose    ${gap > 0 ? "+" : ""}${gap} ${JSON.stringify(token)}`);
      }
      for (const [token, gap] of Object.entries(glossary.delta).slice(0, 12)) {
        console.log(`      glossary ${gap > 0 ? "+" : ""}${gap} ${JSON.stringify(token)}`);
      }
      for (const lesson of blocks.slice(0, 4)) {
        for (const at of lesson.mismatches.slice(0, 2)) {
          console.log(`      blocks   ${lesson.lessonId} #${at.index}`);
          console.log(`        bundle   ${JSON.stringify((at.bundle ?? "").slice(0, 120))}`);
          console.log(`        rendered ${JSON.stringify((at.rendered ?? "").slice(0, 120))}`);
        }
      }
      for (const stray of strays) console.log(`      stray    ${locale}/${stray}`);
    }
    if (args.diffReport) writeFileSync(args.diffReport, canonical(report), "utf8");
    if (!report.clean) {
      console.error("THE BUNDLE DOES NOT CARRY THE WEB'S TEXT — see the differences above");
      return 3;
    }
    console.log("text diff: 0 (prose + glossary multisets, and every lesson block for block)");
    return 0;
  } finally {
    await server.close();
  }
}

process.exitCode = await main();
