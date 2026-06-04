// All user-facing timestamps render in US Eastern (America/New_York), labeled "ET",
// so display is deterministic regardless of the viewer's browser or the SSR server
// timezone (Render runs in UTC). Backend stores/sends UTC; we convert here at the edge.
const TZ = "America/New_York";

function parse(value: string | number | Date | null | undefined): Date | null {
  if (value == null || value === "") return null;
  // Date-only strings (YYYY-MM-DD) must not be shifted across midnight by the TZ
  // conversion, so anchor them at noon UTC (still the same calendar day in ET).
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const d = new Date(value + "T12:00:00Z");
    return isNaN(d.getTime()) ? null : d;
  }
  const d = new Date(value);
  return isNaN(d.getTime()) ? null : d;
}

const isDateOnly = (v: unknown) => typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v);

/** "Jun 4, 2026, 10:42 AM ET" (date-only inputs render without a time). */
export function etDateTime(value: string | number | Date | null | undefined, fallback = "—"): string {
  const d = parse(value);
  if (!d) return fallback;
  if (isDateOnly(value)) return etDate(value, fallback);
  return d.toLocaleString("en-US", {
    timeZone: TZ, year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  }) + " ET";
}

/** "10:42 AM ET" */
export function etTime(value: string | number | Date | null | undefined, fallback = "—"): string {
  const d = parse(value);
  if (!d) return fallback;
  return d.toLocaleTimeString("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit" }) + " ET";
}

/** "Jun 4, 2026" */
export function etDate(value: string | number | Date | null | undefined, fallback = "—"): string {
  const d = parse(value);
  if (!d) return fallback;
  return d.toLocaleDateString("en-US", { timeZone: TZ, year: "numeric", month: "short", day: "numeric" });
}
