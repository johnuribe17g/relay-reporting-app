export function WeekSelector({
  weeks,
  value,
  onChange,
}: {
  weeks: string[];
  value: string | null;
  onChange: (week: string) => void;
}) {
  return (
    <label>
      Week{" "}
      <select
        value={value ?? ""}
        disabled={weeks.length === 0}
        onChange={(event) => onChange(event.target.value)}
      >
        {weeks.length === 0 && <option value="">No weeks</option>}
        {weeks.map((week) => (
          <option key={week} value={week}>
            {week}
          </option>
        ))}
      </select>
    </label>
  );
}
