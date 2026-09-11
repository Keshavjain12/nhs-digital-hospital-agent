/**
 * Display formatting tests.
 *
 * The time-zone cases are the reason this file exists. On a device set to India time the
 * unpinned formatters showed 09:00 UTC as 14:30, which put every clinic between 14:30 and
 * 22:10. These assert hospital time regardless of the zone the tests happen to run in.
 */

import { describe, expect, it } from "vitest";

import { formatDate, languageName, UK_TIME_ZONE, ukDayKey } from "@/lib/format";

const hoursAndMinutes = (iso: string) =>
  new Intl.DateTimeFormat("en-GB", {
    timeZone: UK_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));

describe("UK hospital time", () => {
  it("shows a summer appointment in British Summer Time", () => {
    expect(hoursAndMinutes("2026-09-14T09:00:00Z")).toBe("10:00");
  });

  it("shows a winter appointment in GMT", () => {
    expect(hoursAndMinutes("2026-12-01T09:00:00Z")).toBe("09:00");
  });

  it("puts a slot on the UK day it happens, not the device's day", () => {
    // 23:30 UTC on 14 September is 00:30 on the 15th in London.
    expect(ukDayKey("2026-09-14T23:30:00Z")).toBe("2026-09-15");
    expect(ukDayKey("2026-09-14T09:00:00Z")).toBe("2026-09-14");
  });
});

describe("calendar dates", () => {
  it("never moves a date of birth to the day before", () => {
    expect(formatDate("1974-04-17")).toBe("17/04/1974");
  });
});

describe("language names", () => {
  it("names a language as a clinician would say it", () => {
    expect(languageName("tr")).toBe("Turkish");
    expect(languageName("ar")).toBe("Arabic");
  });

  it("falls back to the code rather than guessing", () => {
    expect(languageName("not a tag!")).toBe("not a tag!");
  });

  it("says so when nothing is recorded", () => {
    expect(languageName(null)).toBe("Not recorded");
  });
});
