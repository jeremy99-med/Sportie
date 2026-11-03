import { dayLabel, todayEastern, windowDays } from "../dates.js";

export default function DayPicker({ selected, onSelect }) {
  const today = todayEastern();
  return (
    <div className="d-flex flex-wrap gap-2 mb-4" role="group" aria-label="Choose a day">
      {windowDays().map((day) => (
        <button
          type="button"
          key={day}
          className={`btn btn-sm ${day === selected ? "btn-primary" : "btn-outline-primary"}`}
          aria-pressed={day === selected}
          aria-label={day === today ? `Today, ${dayLabel(day)}` : dayLabel(day)}
          onClick={() => onSelect(day)}
        >
          {day === today ? "Today" : dayLabel(day).replace(",", "")}
        </button>
      ))}
    </div>
  );
}
