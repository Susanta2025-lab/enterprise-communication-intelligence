import type { Due } from "../api/workItems";

/** Calendar values never pass through Date. */
export function calendarDate(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) throw new Error("Enter a calendar date as YYYY-MM-DD.");
  const [, y, m, d] = match.map(Number);
  const leap = y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (y < 1 || m < 1 || m > 12 || d < 1 || d > days[m - 1]) throw new Error("Enter a valid calendar date.");
  return value;
}
export function zoneFormatter(timezone: string) {
  if (!timezone || timezone.length > 64 || /^[+-]/.test(timezone)) throw new Error("Enter a valid IANA timezone.");
  try { return new Intl.DateTimeFormat("sv-SE", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }); }
  catch { throw new Error("Enter a valid IANA timezone."); }
}
export function wallTime(at: string, timezone: string): string {
  return formattedWallTime(at, zoneFormatter(timezone));
}
function formattedWallTime(at: string, formatter: Intl.DateTimeFormat): string {
  const parts = formatter.formatToParts(new Date(at));
  const get = (type: string) => parts.find(p => p.type === type)?.value;
  return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}:${get("second")}`;
}
/** Enumerate valid offsets and round-trip each instant; never guess a DST fold. */
export function timedChoices(local: string, timezone: string): string[] {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/.test(local)) throw new Error("Enter a local date and time.");
  calendarDate(local.slice(0, 10));
  const formatter = zoneFormatter(timezone);
  const wall = local.length === 16 ? `${local}:00` : local;
  if (+wall.slice(11,13) > 23 || +wall.slice(14,16) > 59 || +wall.slice(17,19) > 59) throw new Error("Enter a valid local time.");
  const choices: string[] = [];
  for (let minutes = -14 * 60; minutes <= 14 * 60; minutes++) {
    const abs = Math.abs(minutes);
    const offset = `${minutes < 0 ? "-" : "+"}${String(Math.floor(abs / 60)).padStart(2,"0")}:${String(abs % 60).padStart(2,"0")}`;
    const at = wall + offset;
    if (formattedWallTime(at, formatter) === wall) choices.push(at);
  }
  return choices;
}
export function dueLabel(due: Due): string {
  if (due.kind === "none") return "No deadline";
  if (due.kind === "date") return `Date-only: ${due.date} (${due.timezone})`;
  try {
  const offset = new Intl.DateTimeFormat("en", { timeZone: due.timezone, timeZoneName: "longOffset" })
    .formatToParts(new Date(due.at)).find(part => part.type === "timeZoneName")?.value ?? "";
  return `Timed: ${wallTime(due.at, due.timezone).replace("T", " ")} (${due.timezone}) ${offset}`;
  } catch {
    return `Timed: ${due.at} (${due.timezone}; timezone unavailable in this browser). The saved server value applies.`;
  }
}

/** An unknown browser zone cannot safely supply an editable local wall time. */
export function editableWallTime(due: Due | undefined): string {
  if (due?.kind !== "datetime") return "";
  try { return wallTime(due.at, due.timezone); }
  catch { return ""; }
}
