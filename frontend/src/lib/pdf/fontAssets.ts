import regular from "@/assets/fonts/liberation-sans/LiberationSans-Regular.ttf?url";
import bold from "@/assets/fonts/liberation-sans/LiberationSans-Bold.ttf?url";
import italic from "@/assets/fonts/liberation-sans/LiberationSans-Italic.ttf?url";
import boldItalic from "@/assets/fonts/liberation-sans/LiberationSans-BoldItalic.ttf?url";

/** The print font as build assets: hashed URLs, fetched on demand, never in the app's JS chunks. */
export const PRINT_FONT_URLS: Record<string, string> = {
  "LiberationSans-Regular.ttf": regular,
  "LiberationSans-Bold.ttf": bold,
  "LiberationSans-Italic.ttf": italic,
  "LiberationSans-BoldItalic.ttf": boldItalic,
};
