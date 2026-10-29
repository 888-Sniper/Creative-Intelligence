type SelectableRange = "all" | "7" | "30" | "90";

const DATE_RANGES = [
  { value: "all", key: "all" },
  { value: "7", key: "d7" },
  { value: "30", key: "d30" },
  { value: "90", key: "d90" },
  // Display a shared window set elsewhere without offering it as a preset.
  { value: "custom", key: "custom" },
] as const;

export function AnalystDateRangeSelect({ value, onChange, t }: {
  value: string;
  onChange: (value: SelectableRange) => void;
  t: (key: string) => string;
}) {
  return (
    <select id="a-range" value={value} onChange={(event) => {
      const next = event.target.value;
      if (next === "all" || next === "7" || next === "30" || next === "90") {
        onChange(next);
      }
    }}>
      {DATE_RANGES.map((range) => (
        <option key={range.value} value={range.value} disabled={range.value === "custom"}>
          {t(`analyst.ranges.${range.key}`)}
        </option>
      ))}
    </select>
  );
}
