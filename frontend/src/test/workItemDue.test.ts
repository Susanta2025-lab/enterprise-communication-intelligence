import { describe, expect, it, vi } from "vitest";
import { calendarDate, dueLabel, editableWallTime, timedChoices } from "../lib/workItemDue";
import { ownedWorkLocation } from "../api/workItems";
describe("strict business deadlines", () => {
  it("preserves date-only calendar values and timezone", () => {
    expect(calendarDate("2028-02-29")).toBe("2028-02-29");
    expect(dueLabel({ kind: "date", date: "2026-09-27", timezone: "Pacific/Kiritimati" })).toBe("Date-only: 2026-09-27 (Pacific/Kiritimati)");
  });
  it.each(["2026-02-29", "2026-04-31", "2026-13-01", "0000-01-01", "2026-01-01T00:00:00Z"])("rejects invalid calendar %s", value => expect(() => calendarDate(value)).toThrow());
  it("rejects DST gaps", () => expect(timedChoices("2026-03-08T02:30", "America/New_York")).toEqual([]));
  it("offers both offsets for a repeated wall time", () => expect(timedChoices("2026-11-01T01:30", "America/New_York")).toEqual(["2026-11-01T01:30:00-05:00", "2026-11-01T01:30:00-04:00"]));
  it("handles a half-hour DST fold", () => expect(timedChoices("2026-04-05T01:45", "Australia/Lord_Howe")).toEqual(["2026-04-05T01:45:00+10:30", "2026-04-05T01:45:00+11:00"]));
  it("renders confirmed timezone instead of browser timezone", () => expect(dueLabel({ kind: "datetime", at: "2026-11-01T06:30:00Z", timezone: "America/New_York" })).toContain("01:30:00 (America/New_York)"));
  it("rejects invalid zones and local times", () => { expect(() => timedChoices("2026-01-01T25:00", "UTC")).toThrow(); expect(() => timedChoices("2026-01-01T12:00", "Invalid/Zone")).toThrow(); });
  it("only accepts owned relative Location references", () => { expect(ownedWorkLocation("https://evil.invalid/api/v1/work-items/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")).toBeNull(); expect(ownedWorkLocation("/api/v1/work-items/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")).toBe("/tracking/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"); });
});


describe("timezone database and unusual offset boundaries", () => {
  it.each([
    ["2026-10-04T02:15", "Australia/Lord_Howe"],
    ["2011-12-30T12:00", "Pacific/Apia"],
    ["1900-01-01T12:00", "Europe/Paris"],
  ])("fails closed for gaps or historical sub-minute offsets: %s %s", (local, zone) => {
    expect(timedChoices(local, zone)).toEqual([]);
  });
  it.each([
    ["Pacific/Kiritimati", "+14:00"],
    ["Etc/GMT+12", "-12:00"],
    ["Asia/Kathmandu", "+05:45"],
  ])("preserves the explicit extreme/non-hour offset in %s", (zone, offset) => {
    expect(timedChoices("2026-09-27T12:00", zone)).toEqual([`2026-09-27T12:00:00${offset}`]);
  });
  it("keeps a saved server deadline readable when the browser lacks its zone", () => {
    const due = { kind: "datetime" as const, at: "2026-09-27T12:00:00+00:00", timezone: "UTC" };
    const formatter = vi.spyOn(Intl, "DateTimeFormat").mockImplementation(() => { throw new RangeError("Unsupported zone"); });
    try {
      expect(dueLabel(due)).toContain(due.at);
      expect(dueLabel(due)).toContain("timezone unavailable in this browser");
      expect(editableWallTime(due)).toBe("");
    } finally { formatter.mockRestore(); }
  });
});
