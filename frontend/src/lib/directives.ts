import { directiveFromMarkdown } from "mdast-util-directive";
import { directive } from "micromark-extension-directive";
import type { Root } from "mdast";
import type { Plugin } from "unified";

/**
 * The course's directive dialect: `remark-directive` minus its INLINE `:name` syntax.
 *
 * The course writes only block directives (`:::note`, `::figure`, `::exercise`), and the inline
 * dialect silently ate any colon-plus-alphanumeric in the prose — `03:00` parsed as a childless
 * `:00` directive, so every surface printed `03`. Dropping the construct is what makes a clock time
 * literal text again, on both surfaces at once, since they share this parser.
 */
export const remarkBlockDirectives: Plugin<[], Root> = function () {
  const data = this.data();
  const syntax = directive();
  delete syntax.text;
  (data.micromarkExtensions ??= []).push(syntax);
  (data.fromMarkdownExtensions ??= []).push(directiveFromMarkdown());
};
