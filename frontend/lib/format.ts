/**
 * Display formatting: dates, times and languages.
 *
 * Every time this service shows is a UK hospital time, so every time formatter pins
 * Europe/London instead of using whatever zone the viewer's device is set to. The first
 * version did not, and on a machine set to India time the booking page offered clinics at
 * 22:10 - the right instant, shown in the wrong zone. For a hospital that is a correctness
 * problem rather than a cosmetic one: a patient whose phone is set to the wrong zone would be
 * told the wrong time for their appointment.
 */

export const UK_TIME_ZONE = "Europe/London";

/**
 * A calendar date with no time of day, such as a date of birth ("1974-04-17").
 *
 * Formatted in UTC, not the UK zone. `new Date("1974-04-17")` is midnight UTC, and rendering
 * that instant in any zone west of Greenwich shows the day before. A date of birth has no
 * time of day, so there is no zone in which it should move.
 */
const calendarDate = new Intl.DateTimeFormat("en-GB", {
  timeZone: "UTC",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

export function formatDate(isoDate: string): string {
  return calendarDate.format(new Date(isoDate));
}

const dayKeyParts = new Intl.DateTimeFormat("en-GB", {
  timeZone: UK_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

/** The UK calendar day an instant falls on, as YYYY-MM-DD. For grouping, not display. */
export function ukDayKey(iso: string): string {
  const parts = Object.fromEntries(
    dayKeyParts.formatToParts(new Date(iso)).map((part) => [part.type, part.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}`;
}

const languageNames =
  typeof Intl.DisplayNames === "function"
    ? new Intl.DisplayNames(["en-GB"], { type: "language" })
    : null;

/**
 * A language code as a clinician would say it: "tr" becomes "Turkish".
 *
 * Records store BCP 47 codes, and the working list and patient record used to print them
 * raw - "Interpreter: pl-PL" is not something anyone arranging an interpreter should have to
 * decode. Falls back to the code itself, rather than guessing, when it is not recognised.
 */
export function languageName(code: string | null | undefined): string {
  if (!code) return "Not recorded";
  try {
    const name = languageNames?.of(code);
    if (name && name.toLowerCase() !== code.toLowerCase()) return name;
  } catch {
    // An invalid tag throws a RangeError. The raw value is better than nothing.
  }
  return code;
}
