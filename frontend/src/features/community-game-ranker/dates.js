// Game days are US Eastern calendar dates (YYYY-MM-DD), matching the API's ?date= parameter.

// Days shown either side of today. Keep in sync with WINDOW_DAYS in the backend's ingest.py.
const WINDOW_DAYS = 5;

// en-CA formats dates as YYYY-MM-DD.
export const todayEastern = () =>
  new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(new Date());

// Date strings are handled as UTC midnight so adding days never crosses a local DST change.
const parseDay = (day) => new Date(`${day}T00:00:00Z`);

function addDays(day, count) {
  const next = parseDay(day);
  next.setUTCDate(next.getUTCDate() + count);
  return next.toISOString().slice(0, 10);
}

export function windowDays() {
  const today = todayEastern();
  return Array.from({ length: WINDOW_DAYS * 2 + 1 }, (_, i) => addDays(today, i - WINDOW_DAYS));
}

// e.g. "Wed, Nov 4"
export const dayLabel = (day) =>
  parseDay(day).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
