import { format } from "date-fns";

/** Always European format: DD/MM/YYYY, 24-hour clock, in both locales. Never US format. */
export function formatDateTime(iso: string): string {
  return format(new Date(iso), "dd/MM/yyyy HH:mm");
}

export function formatDate(iso: string): string {
  return format(new Date(iso), "dd/MM/yyyy");
}
