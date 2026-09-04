import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import { eligibleText, REF_PATTERN } from "@/lib/glossary/annotate";
import type { RefKind, RefRegistry } from "@/lib/refs/registry";

/**
 * The module and lesson references in EXERCISE prose, resolved at export time.
 *
 * A lesson's references travel as `lessonRef` nodes inside its mdast, because a lesson travels as an
 * mdast. An exercise's prose does not — it is a short inline string inside a generator config, and
 * the app draws it with its own inline renderer. So the marks travel beside the string instead, as
 * OFFSETS INTO IT, and the app stops carrying a detector of its own.
 *
 * The detector is `annotate.ts`'s: the same `REF_PATTERN` and the same `eligibleText` walk the lesson
 * annotator uses, so a token that is a reference in a lesson is a reference here and one that is
 * skipped is skipped here — code spans, headings and link text included. Two detectors would be two
 * opinions about which words a reader may tap, which is the thing this repository refuses.
 *
 * One rule is deliberately NOT shared. A lesson does not link a mention of itself, because it would
 * send the reader where they already are; an exercise links everything it resolves. An exercise is
 * shown inside an exam as readily as inside its own lesson, and in an exam there is no page for a
 * mention to be self-referential to.
 */

const processor = unified().use(remarkParse).use(remarkGfm);

export interface ExerciseRefMark {
  /** Offsets into the exact string the bundle carries, so the app never searches for the token. */
  start: number;
  end: number;
  mention: string;
  refKind: RefKind;
  refId: string;
}

export class ExerciseRefError extends Error {}

/** Every resolvable reference in one exercise string, in reading order. */
export function exerciseRefs(text: string, registry: RefRegistry): ExerciseRefMark[] {
  const tree = processor.parse(text);
  const marks: ExerciseRefMark[] = [];
  for (const { node } of eligibleText(tree)) {
    const base = node.position?.start.offset;
    if (base === undefined) {
      throw new ExerciseRefError(`no source position for a text node of ${JSON.stringify(text)}`);
    }
    for (const match of node.value.matchAll(REF_PATTERN)) {
      const target = registry.resolve(match[0]);
      if (!target) continue;
      const start = base + match.index;
      const end = start + match[0].length;
      // The offset is `where the node starts` + `where the match sits inside its value`, which is
      // only the same thing while the value maps character for character onto the source. It does
      // for every string in the course; an escape or an entity earlier in the node would break it
      // silently, and a silently wrong offset puts the chip on the wrong word. So it is READ BACK.
      if (text.slice(start, end) !== match[0]) {
        throw new ExerciseRefError(
          `offset ${start} of ${JSON.stringify(text)} is ${JSON.stringify(text.slice(start, end))}, ` +
            `not the ${JSON.stringify(match[0])} the annotator found there`,
        );
      }
      marks.push({ start, end, mention: match[0], refKind: target.kind, refId: target.id });
    }
  }
  return marks;
}
